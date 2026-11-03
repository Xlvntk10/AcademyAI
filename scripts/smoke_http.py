"""Local HTTP smoke test on a disposable database copy, never on personal progress.

Run after frontend build with ports 8000 and 4173 free. Only processes created
by this script are stopped; their logs and the test database remain ignored.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import httpx

from scripts.prepare_db import ROOT, backup, snapshot, verify


def run():
    for port in (8000, 4173):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"Port {port} is in use. Stop your local dev server first.")
    node = shutil.which("node")
    if not node or not (ROOT / "frontend/dist/sw.js").exists():
        raise RuntimeError("Node and a production frontend build are required.")
    source = ROOT / "database.db"
    original = snapshot(source)
    folder = ROOT / ".test-artifacts" / ("http-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(parents=True)
    database = folder / "smoke.db"
    backup(source, database)
    env = {**os.environ, "ACADEMY_DATABASE_URL": "sqlite:///" + database.as_posix(), "PYTHONUTF8": "1"}
    processes = []
    logs = []

    def launch(args, name, cwd=ROOT):
        log = (folder / f"{name}.log").open("w", encoding="utf8")
        logs.append(log)
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        processes.append(process)
        return process

    def wait(client, url):
        for _ in range(60):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        raise RuntimeError(f"Server did not become ready: {url}. Logs: {folder}")

    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    try:
        backend_args = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
        backend = launch(backend_args, "api")
        launch([node, "node_modules/vite/bin/vite.js", "preview", "--host", "127.0.0.1"], "frontend", ROOT / "frontend")
        with httpx.Client(base_url="http://127.0.0.1:4173", timeout=15, trust_env=False) as client:
            wait(client, "http://127.0.0.1:8000/api/health")
            wait(client, "/")

            def get(url):
                response = client.get(url)
                assert response.status_code == 200, response.text
                return response.json()

            def post(url, body):
                response = client.post(url, json=body)
                assert response.status_code == 200, response.text
                return response.json()

            health = get("/api/health")
            lessons = get("/api/lessons")
            assert len(lessons) == 20
            before = get("/api/dashboard")
            from datetime import date, timedelta
            today = date.fromisoformat(before["today"])
            start = today - timedelta(days=today.weekday())
            week = post("/api/planner/generate", {"week_start": start.isoformat()})
            lesson_task = next((t for t in week["tasks"] if t["scheduled_date"] == today.isoformat() and t["kind"] == "lesson"), None)
            slug = lesson_task["lesson_slug"] if lesson_task else lessons[0]["slug"]
            lesson = get(f"/api/lessons/{slug}")
            request_id = str(uuid4())
            attempt = post(f"/api/lessons/{slug}/runs", {"request_id": request_id})
            with sqlite3.connect(database) as db:
                keys = dict(db.execute("SELECT id,correct_answer FROM exercise"))
            for exercise in lesson["exercises"]:
                attempt = post(f"/api/runs/{attempt['id']}/answers", {"exercise_id": exercise["id"], "answer": keys[exercise["id"]]})
            assert attempt["completed_at"] and attempt["score"] == lesson["max_score"]
            # A network retry must neither change the run nor add XP.
            assert post(f"/api/lessons/{slug}/runs", {"request_id": request_id}) == attempt
            if lesson_task:
                task_url = f"/api/planner/tasks/{lesson_task['id']}/complete"
                assert post(task_url, {"actual_minutes": 17})["actual_minutes"] == 17
                assert post(task_url, {"actual_minutes": 99})["actual_minutes"] == 17
            words = get("/api/vocabulary")
            word = next(w for w in words["words"] if w["lesson_slug"] == slug)
            post(f"/api/vocabulary/{word['id']}/add", {})
            # Existing personal review dates are respected in the copied database too.
            words = get("/api/vocabulary")
            due = next((w for w in words["words"] if w["added"] and w["due_on"] <= words["today"]), None)
            if due:
                result = post(f"/api/vocabulary/{due['id']}/review", {"request_id": str(uuid4()), "answer": due["term"]})
                assert result["is_correct"]
            vocabulary_saved = get("/api/vocabulary")
            saved = get("/api/dashboard")
            assert saved["total_xp"] >= before["total_xp"]
            assert saved == get("/api/dashboard")

            html = client.get("/")
            assert "text/html" in html.headers["content-type"]
            manifest = get("/manifest.webmanifest")
            assert manifest["display"] == "standalone"
            worker = client.get("/sw.js")
            assert "javascript" in worker.headers["content-type"]
            paths = json.loads(re.search(r"const PRECACHE = (\[.*?\]);", worker.text).group(1))
            assert "__VERSION__" not in worker.text and "/index.html" in paths
            for path in paths:
                response = client.get(path)
                assert response.status_code == 200, path
                if path.endswith(".png"):
                    assert response.content.startswith(b"\x89PNG"), path
                elif path.endswith(".js"):
                    assert "javascript" in response.headers["content-type"], path
            stop(backend)
            launch(backend_args, "api-restarted")
            wait(client, "http://127.0.0.1:8000/api/health")
            assert get("/api/dashboard") == saved
            assert get(f"/api/runs/{attempt['id']}") == attempt
            assert get("/api/vocabulary") == vocabulary_saved
            verify(database)
            assert snapshot(source) == original, "Production database changed during smoke test"
            print(json.dumps({"health": health, "lessons": len(lessons), "completed_slug": slug,
                "score": attempt["score"], "saved_after_restart": True,
                "static_assets_verified": len(paths), "production_database_unchanged": True,
                "artifacts": str(folder)}, ensure_ascii=False, indent=2))
    finally:
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()


if __name__ == "__main__":
    run()
