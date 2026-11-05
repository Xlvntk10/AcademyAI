"""Serve the production PWA and API on one HTTPS origin with first-party cookies."""
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
ROUTES = {"", "today", "learn", "plan", "progress"}


def mount_frontend(application, directory=DIST):
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build frontend/dist before serving the production PWA")

    @application.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        candidate = (directory / path).resolve()
        if not candidate.is_relative_to(directory):
            raise HTTPException(404)
        if path.strip("/") in ROUTES:
            candidate = directory / "index.html"
        if not candidate.is_file():
            raise HTTPException(404)
        # Revalidate shell/worker every time. Vite assets carry content hashes.
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        headers = {"Cache-Control": cache}
        if path == "sw.js":
            headers["Service-Worker-Allowed"] = "/"
        return FileResponse(candidate, headers=headers)
