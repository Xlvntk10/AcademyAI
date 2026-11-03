"""Mastery is a saved objective score, never a claimed CEFR/IELTS certification."""
from collections import defaultdict
from sqlalchemy import func
from sqlmodel import select
from app.database.models import Attempt, Exercise, ExerciseContent, LessonContent, LessonPrerequisite, LessonRun, RunAnswer


def curriculum_state(session):
    totals = dict(session.exec(select(Exercise.lesson_id, func.sum(Exercise.points)).join(ExerciseContent,
        ExerciseContent.exercise_id == Exercise.id).group_by(Exercise.lesson_id)).all())
    best = defaultdict(int)
    rows = session.exec(select(LessonRun.lesson_id, LessonRun.id, func.sum(Attempt.earned_points))
        .join(RunAnswer, RunAnswer.run_id == LessonRun.id).join(Attempt, Attempt.id == RunAnswer.attempt_id)
        .where(LessonRun.completed_at.is_not(None)).group_by(LessonRun.lesson_id, LessonRun.id)).all()
    for lesson_id, _, score in rows:
        best[lesson_id] = max(best[lesson_id], score)
    mastered = {lesson_id for lesson_id, score in best.items() if totals.get(lesson_id, 0) > 0 and score * 100 >= totals[lesson_id] * 80}
    slugs = dict(session.exec(select(LessonContent.lesson_id, LessonContent.slug)).all())
    requirements = defaultdict(list)
    for gate in session.exec(select(LessonPrerequisite)).all():
        if gate.prerequisite_id not in mastered:
            requirements[gate.lesson_id].append(slugs[gate.prerequisite_id])
    existing = set(session.exec(select(LessonRun.lesson_id)).all())
    return {lesson_id: dict(mastered=lesson_id in mastered, unlocked=not requirements[lesson_id] or lesson_id in existing,
        prerequisites=requirements[lesson_id], best_percent=round(best[lesson_id]/total*100,1) if total else 0)
        for lesson_id, total in totals.items()}
