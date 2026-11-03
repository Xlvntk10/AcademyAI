import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest

SLUG = "a2-daily-routine"
ANSWERS = ["studies", "doesn't drink", "Do", "At half past seven.", "I study English every day.", "No, she doesn't."]


def start(client, request_id=None):
    response = client.post(f"/api/lessons/{SLUG}/runs", json={"request_id": request_id or str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def exercises(client):
    return client.get(f"/api/lessons/{SLUG}/exercises").json()


def test_catalog_has_theory_but_no_answer_keys(client):
    assert client.get("/api/health").json()["status"] == "ok"
    lessons = client.get("/api/lessons").json()
    assert len(lessons) == 20
    assert lessons[0]["max_score"] == 60
    lesson = client.get(f"/api/lessons/{SLUG}").json()
    assert len(lesson["theory"]) == 6
    assert len(lesson["exercises"]) == 6
    for exercise in lesson["exercises"]:
        assert "correct_answer" not in exercise
        assert "accepted_answers" not in exercise
        assert "explanation" not in exercise
    assert client.get("/api/progress").json()["total_xp"] == 0


def test_server_grades_saves_and_restores_completed_lesson(client, database):
    run = start(client)
    items = exercises(client)
    submitted = ["study", *ANSWERS[1:]]  # One deliberately incorrect answer.
    for item, answer in zip(items, submitted):
        response = client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": item["id"], "answer": answer})
        assert response.status_code == 200, response.text
        result = response.json()
    assert result["score"] == 50
    assert result["correct_count"] == 5
    assert result["completed_at"].endswith("Z")
    assert result["answers"][0]["earned_points"] == 0
    assert result["answers"][0]["correct_answer"] == "studies"
    assert result["answers"][0]["explanation"]
    assert client.get(f'/api/runs/{run["id"]}').json() == result
    stats = client.get(f"/api/lessons/{SLUG}/stats").json()
    assert stats["last_result"] == result
    assert stats["active_run_id"] is None
    assert stats["best_score"] == 50
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM attempt").fetchone()[0] == 6
        assert db.execute("SELECT count(*) FROM runanswer").fetchone()[0] == 6


def test_retries_and_multiple_tabs_do_not_duplicate_points(client, database):
    request_id = str(uuid4())
    run = start(client, request_id)
    assert start(client, request_id)["id"] == run["id"]
    assert start(client)["id"] == run["id"]
    item = exercises(client)[0]
    body = {"exercise_id": item["id"], "answer": "studies"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(f'/api/runs/{run["id"]}/answers', json=body), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert all(r.json()["score"] == 10 for r in responses)
    assert client.post(f'/api/runs/{run["id"]}/answers', json={**body, "answer": "study"}).status_code == 409
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM attempt").fetchone()[0] == 1
    stats = client.get(f"/api/lessons/{SLUG}/stats").json()
    assert stats["active_run_id"] == run["id"]
    assert stats["completed_runs"] == 0
    assert client.get("/api/progress").json()["total_xp"] == 0


def test_xp_is_best_completed_result_not_sum_of_retries(client):
    for _ in range(2):
        run = start(client)
        for item, answer in zip(exercises(client), ANSWERS):
            assert client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": item["id"], "answer": answer}).status_code == 200
    progress = client.get("/api/progress").json()
    assert progress["completed_runs"] == 2
    assert progress["completed_lessons"] == 1
    assert progress["total_xp"] == 60


@pytest.mark.parametrize("answer", ["  do  ", "DO", "Do."])
def test_text_normalization(client, answer):
    run = start(client)
    item = exercises(client)[2]
    response = client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": item["id"], "answer": answer})
    assert response.json()["answers"][0]["is_correct"] is True


@pytest.mark.parametrize("extra", [{"is_correct": True}, {"earned_points": 999}, {"score": 999}])
def test_client_cannot_supply_grades(client, extra):
    run = start(client)
    item = exercises(client)[0]
    assert client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": item["id"], "answer": "study", **extra}).status_code == 422
    assert client.get(f'/api/runs/{run["id"]}').json()["answered_count"] == 0


def test_invalid_inputs_and_unknown_resources(client):
    run = start(client)
    item = exercises(client)[0]
    for answer in ["", "   ", "x" * 501, "not an option"]:
        assert client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": item["id"], "answer": answer}).status_code == 422
    assert client.post(f'/api/runs/{run["id"]}/answers', json={"exercise_id": 999, "answer": "x"}).status_code == 404
    assert client.get("/api/lessons/missing").status_code == 404
    assert client.get(f"/api/runs/{uuid4()}").status_code == 404
    assert client.get("/api/runs/not-a-uuid").status_code == 422
