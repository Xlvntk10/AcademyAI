"""Server-side grading and progress, isolated from legacy demo attempts."""
from datetime import timezone
import unicodedata
from fastapi import HTTPException
from sqlmodel import Session, select
from app.database.models import Attempt, Exercise, ExerciseContent, Lesson, LessonContent, LessonMeta, LessonRun, RunAnswer


def normalize(answer: str, case_sensitive: bool = False) -> str:
    if case_sensitive:
        return answer.strip()
    answer = unicodedata.normalize("NFKC", answer).replace("’", "'").casefold()
    return " ".join(answer.split()).rstrip(".!? ")


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def lesson_by_slug(session: Session, slug: str):
    row = session.exec(select(Lesson, LessonContent).join(LessonContent).where(LessonContent.slug == slug)).first()
    if row is None:
        raise HTTPException(404, "Урок не найден")
    return row


def exercises_for(session: Session, lesson_id: int):
    return session.exec(select(Exercise, ExerciseContent).join(ExerciseContent)
        .where(Exercise.lesson_id == lesson_id).order_by(ExerciseContent.position)).all()


def lesson_summary(session, lesson, content):
    exercises = exercises_for(session, lesson.id)
    meta = session.get(LessonMeta, lesson.id)
    return dict(id=lesson.id, slug=content.slug, title=lesson.title, level=lesson.level,
        summary=content.summary, duration_minutes=content.duration_minutes, version=content.version,
        exercise_count=len(exercises), max_score=sum(e.points for e, _ in exercises),
        subject=meta.subject if meta else "english", topic=meta.topic if meta else "English", position=meta.position if meta else 0)


def exercise_public(exercise, content):
    return dict(id=exercise.id, question=exercise.question, points=exercise.points,
        position=content.position, kind=content.kind, options=content.options)


def get_run(session, run_id):
    run = session.get(LessonRun, str(run_id))
    if run is None:
        raise HTTPException(404, "Прохождение не найдено")
    return run


def run_result(session, run):
    content = session.get(LessonContent, run.lesson_id)
    rows = session.exec(select(Attempt, Exercise, ExerciseContent).select_from(RunAnswer)
        .join(Attempt, Attempt.id == RunAnswer.attempt_id)
        .join(Exercise, Exercise.id == RunAnswer.exercise_id)
        .join(ExerciseContent, ExerciseContent.exercise_id == Exercise.id)
        .where(RunAnswer.run_id == run.id).order_by(ExerciseContent.position)).all()
    exercises = exercises_for(session, run.lesson_id)
    answers = [dict(exercise_id=e.id, answer=a.answer, is_correct=a.is_correct, earned_points=a.earned_points,
        correct_answer=e.correct_answer, explanation=c.explanation) for a, e, c in rows]
    return dict(id=run.id, lesson_slug=content.slug, started_at=utc(run.started_at), completed_at=utc(run.completed_at),
        answered_count=len(rows), exercise_count=len(exercises), score=sum(a.earned_points for a, _, _ in rows),
        max_score=sum(e.points for e, _ in exercises), correct_count=sum(a.is_correct for a, _, _ in rows), answers=answers)


def lesson_stats(session, lesson, content):
    runs = session.exec(select(LessonRun).where(LessonRun.lesson_id == lesson.id)
        .order_by(LessonRun.started_at.desc(), LessonRun.id.desc())).all()
    completed = sorted((r for r in runs if r.completed_at), key=lambda r: r.completed_at, reverse=True)
    results = [run_result(session, r) for r in completed]
    return dict(slug=content.slug, completed_runs=len(completed), best_score=max((r["score"] for r in results), default=0),
        max_score=sum(e.points for e, _ in exercises_for(session, lesson.id)),
        active_run_id=next((r.id for r in runs if r.completed_at is None), None),
        last_result=results[0] if results else None)
