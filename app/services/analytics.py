"""Progress derived from durable facts. Lesson XP is the best completed score.
Practice grants at most 10 XP per subject/local day, even after plan rebuilds.
"""
from collections import defaultdict
from datetime import timedelta
from sqlmodel import select
from app.database.models import Attempt, LessonContent, LessonMeta, LessonRun, RunAnswer, StudyTask, VocabularyReview
from app.services import clock
from app.services.planner import monday, settings


def streaks(days, today):
    days = sorted(set(d for d in days if d <= today))
    longest = current = 0
    earned_seven = previous = None
    for day in days:
        current = current + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, current)
        if current >= 7 and earned_seven is None:
            earned_seven = day
        previous = day
    active = 0
    cursor = today if today in days else today - timedelta(days=1)
    day_set = set(days)
    while cursor in day_set:
        active += 1
        cursor -= timedelta(days=1)
    return active, longest, earned_seven


def accuracy(correct, total):
    return round(correct / total * 100, 1) if total else None


def dashboard(session):
    today = clock.local_day()
    prefs = settings(session)
    meta = {m.lesson_id: m for m in session.exec(select(LessonMeta)).all()}
    published = set(session.exec(select(LessonContent.lesson_id)).all())
    runs = {r.id: r for r in session.exec(select(LessonRun)).all() if r.lesson_id in published}
    answer_rows = session.exec(select(Attempt, RunAnswer).join(RunAnswer, RunAnswer.attempt_id == Attempt.id)).all()
    tasks = session.exec(select(StudyTask).where(StudyTask.status == "completed")).all()
    days = defaultdict(lambda: dict(answers=0, correct_answers=0, completed_runs=0, tasks=0, minutes=0, practice_xp=0, vocabulary_reviews=0))
    subjects = {s: dict(subject=s, completed_lessons=0, available_lessons=sum(m.subject == s and m.lesson_id in published for m in meta.values()),
        answers=0, correct_answers=0, minutes=0, lesson_xp=0) for s in ("english", "python")}
    scores = defaultdict(int)
    for attempt, link in answer_rows:
        run = runs.get(link.run_id)
        if not run or clock.local_day(attempt.created_at) > today:
            continue
        subject = meta[run.lesson_id].subject if run.lesson_id in meta else "english"
        day = clock.local_day(attempt.created_at)
        days[day]["answers"] += 1
        days[day]["correct_answers"] += int(attempt.is_correct)
        subjects[subject]["answers"] += 1
        subjects[subject]["correct_answers"] += int(attempt.is_correct)
        scores[run.id] += attempt.earned_points
    completed = sorted((r for r in runs.values() if r.completed_at and clock.local_day(r.completed_at) <= today), key=lambda r: r.completed_at)
    best = {}
    first_completion = {}
    for run in completed:
        day = clock.local_day(run.completed_at)
        days[day]["completed_runs"] += 1
        best[run.lesson_id] = max(best.get(run.lesson_id, 0), scores[run.id])
        first_completion.setdefault(run.lesson_id, day)
    for lesson_id, score in best.items():
        subject = meta[lesson_id].subject if lesson_id in meta else "english"
        subjects[subject]["completed_lessons"] += 1
        subjects[subject]["lesson_xp"] += score
    practice_days = set()
    minute_events = []
    week_start = monday(today)
    weekly_subject = dict(english=0, python=0)
    for task in tasks:
        if not task.completed_at or clock.local_day(task.completed_at) > today:
            continue
        day = clock.local_day(task.completed_at)
        minutes = task.actual_minutes or 0
        days[day]["tasks"] += 1
        days[day]["minutes"] += minutes
        subjects[task.subject]["minutes"] += minutes
        minute_events.append((day, minutes))
        if week_start <= day <= today:
            weekly_subject[task.subject] += minutes
        if task.kind in ("practice", "review"):
            practice_days.add((day, task.subject))
    for day, _ in practice_days:
        days[day]["practice_xp"] += 10
    for review in session.exec(select(VocabularyReview)).all():
        day = clock.local_day(review.reviewed_at)
        if day <= today:
            days[day]["vocabulary_reviews"] += 1
    active_days = {day for day, row in days.items() if row["answers"] or row["tasks"] or row["completed_runs"] or row["vocabulary_reviews"]}
    current, longest, seven_on = streaks(active_days, today)
    english_days = sorted(day for lesson_id, day in first_completion.items() if meta.get(lesson_id) and meta[lesson_id].subject == "english")
    python_days = sorted(day for lesson_id, day in first_completion.items() if meta.get(lesson_id) and meta[lesson_id].subject == "python")
    total_minutes = sum(t[1] for t in minute_events)
    cumulative = 0
    dedicated_on = None
    for day, minutes in sorted(minute_events):
        cumulative += minutes
        if cumulative >= 600 and dedicated_on is None:
            dedicated_on = day
    achievements = [
        dict(code="first_step", title="First Step", description="Заверши первый урок", target=1, progress=min(1, len(best)), unlocked_on=min(first_completion.values(), default=None), reward="Значок «Первый шаг»"),
        dict(code="seven_days", title="Seven Days", description="Занимайся 7 календарных дней подряд", target=7, progress=min(7, longest), unlocked_on=seven_on, reward="Значок «Постоянство»"),
        dict(code="english_explorer", title="English Explorer", description="Заверши 10 разных уроков английского", target=10, progress=min(10, len(english_days)), unlocked_on=english_days[9] if len(english_days) >= 10 else None, reward="Значок «Исследователь языка»"),
        dict(code="python_beginner", title="Python Beginner", description="Заверши первый урок Python", target=1, progress=min(1, len(python_days)), unlocked_on=python_days[0] if python_days else None, reward="Значок «Первые строки»"),
        dict(code="dedicated_student", title="Dedicated Student", description="Подтверди 10 часов занятий в заданиях плана", target=600, progress=min(600, total_minutes), unlocked_on=dedicated_on, reward="Значок «10 часов для будущего»"),
    ]
    lesson_xp = sum(best.values())
    practice_xp = len(practice_days) * 10
    total_xp = lesson_xp + practice_xp
    level = 1 + total_xp // 100
    week_rows = [row for day, row in days.items() if week_start <= day <= today]
    weekly = {key: sum(row[key] for row in week_rows) for key in ("minutes", "answers", "correct_answers", "completed_runs")}
    answers = sum(s["answers"] for s in subjects.values())
    correct = sum(s["correct_answers"] for s in subjects.values())
    return dict(today=today, timezone="Asia/Almaty", total_xp=total_xp, lesson_xp=lesson_xp, practice_xp=practice_xp,
        level=level, level_title="Первый шаг" if level < 3 else "Исследователь" if level < 6 else "Уверенный ученик",
        xp_in_level=total_xp % 100, xp_to_next_level=100-total_xp % 100,
        current_streak=current, longest_streak=longest, completed_lessons=len(best), completed_runs=len(completed),
        answers=answers, correct_answers=correct, accuracy=accuracy(correct, answers), minutes=total_minutes,
        daily_goal=dict(target_minutes=prefs.daily_goal_minutes, completed_minutes=days[today]["minutes"], reached=days[today]["minutes"] >= prefs.daily_goal_minutes),
        weekly_goal=dict(target_minutes=prefs.weekly_goal_minutes, completed_minutes=weekly["minutes"], reached=weekly["minutes"] >= prefs.weekly_goal_minutes),
        subjects=[{**s, "accuracy": accuracy(s["correct_answers"], s["answers"])} for s in subjects.values()], achievements=achievements,
        activity=[dict(date=today-timedelta(days=i), **days[today-timedelta(days=i)]) for i in reversed(range(84))],
        weekly_report=dict(start=week_start, end=week_start+timedelta(days=6), active_days=sum(week_start <= d <= today for d in active_days),
            **weekly, accuracy=accuracy(weekly["correct_answers"], weekly["answers"]), english_minutes=weekly_subject["english"], python_minutes=weekly_subject["python"]))
