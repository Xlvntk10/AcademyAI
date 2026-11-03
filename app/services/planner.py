"""Deterministic scheduling against the real published catalogue."""
from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException
from sqlmodel import select
from app.database.models import Lesson, LessonContent, LessonMeta, LessonRun, PlanWeek, StudySettings, StudyTask, TaskMove
from app.services import clock
from app.services.mastery import curriculum_state

PRACTICE = {
    "english": [
        ("IELTS: привычка читать", "Прочитай короткий английский текст уровня A2. Выпиши 5 полезных слов, затем перескажи основную мысль в трёх простых предложениях. Это самостоятельная практика, без оценки IELTS."),
        ("Английский: мой день", "Напиши 6 предложений о своём обычном дне. Используй I usually, I don't, She studies. Проверь окончания -s и порядок слов."),
        ("Английский: говори вслух", "Расскажи вслух об учёбе и увлечениях в течение минуты. Повтори рассказ, исправив заметные ошибки. Автоматическая оценка речи пока не подключена."),
    ],
    "python": [
        ("Python: чтение кода", "На бумаге запиши переменную score = 10, затем score = score + 5. Объясни своими словами, как меняется значение. Напиши ещё два похожих примера."),
        ("Алгоритмы: разбей задачу на шаги", "Опиши по шагам, как найти самое большое число в списке. Проверь свой алгоритм на [3, 1, 8, 2] и на списке из одного числа. Исполнять код не требуется."),
        ("Python: повторение", "Повтори конспект последнего урока Python. Составь 3 вопроса по теме и ответь без подсказок. Если ещё не начинал — объясни разницу между числом 5 и строкой '5'."),
    ],
}


def monday(day):
    return day - timedelta(days=day.weekday())


def settings(session):
    result = session.get(StudySettings, 1)
    if result is None:
        raise HTTPException(503, "Выполните миграцию базы для планировщика")
    return result


def task_read(session, task):
    content = session.get(LessonContent, task.lesson_id) if task.lesson_id else None
    return dict(**{key: getattr(task, key) for key in ("id", "scheduled_date", "original_date", "subject", "kind",
        "title", "instructions", "planned_minutes", "status", "actual_minutes")},
        completed_at=clock.as_utc(task.completed_at) if task.completed_at else None,
        lesson_slug=content.slug if content else None,
        overdue=task.status == "pending" and task.scheduled_date < clock.local_day())


def week_read(session, start):
    start = monday(start)
    tasks = session.exec(select(StudyTask).where(StudyTask.scheduled_date >= start,
        StudyTask.scheduled_date < start + timedelta(days=7), StudyTask.status != "cancelled")
        .order_by(StudyTask.scheduled_date, StudyTask.created_at, StudyTask.id)).all()
    overdue = session.exec(select(StudyTask).where(StudyTask.scheduled_date < clock.local_day(),
        StudyTask.status == "pending").order_by(StudyTask.scheduled_date).limit(100)).all()
    return dict(week_start=start, today=clock.local_day(), generated=session.get(PlanWeek, start) is not None,
        settings=settings(session).model_dump(exclude={"id"}),
        tasks=[task_read(session, t) for t in tasks], overdue=[task_read(session, t) for t in overdue],
        planned_minutes=sum(t.planned_minutes for t in tasks),
        completed_minutes=sum(t.actual_minutes or 0 for t in tasks if t.status == "completed"))


def generate(session, start, replace_pending=False, fill_existing=False):
    today = clock.local_day()
    if start != monday(start) or start < monday(today) or start > monday(today) + timedelta(weeks=52):
        raise HTTPException(422, "Выберите понедельник текущей или будущей недели, не далее года")
    plan = session.get(PlanWeek, start)
    if plan and not replace_pending and not fill_existing:
        return
    if plan:
        # Preserve completed tasks, overdue tasks and rescheduling history.
        for task in session.exec(select(StudyTask).where(StudyTask.plan_week == start,
            StudyTask.status == "pending", StudyTask.scheduled_date >= today,
            StudyTask.scheduled_date >= start, StudyTask.scheduled_date < start + timedelta(days=7))).all() if replace_pending else []:
            task.status = "cancelled"
            session.add(task)
        plan.revision += 1
    else:
        plan = PlanWeek(week_start=start, created_at=clock.now())
    session.add(plan)
    session.flush()
    prefs = settings(session)
    catalogue = session.exec(select(Lesson, LessonContent, LessonMeta).join(LessonContent)
        .join(LessonMeta, LessonMeta.lesson_id == Lesson.id).order_by(LessonMeta.position, Lesson.id)).all()
    completed = set(session.exec(select(LessonRun.lesson_id).where(LessonRun.completed_at.is_not(None))).all())
    assigned = set(session.exec(select(StudyTask.lesson_id).where(StudyTask.status == "pending", StudyTask.lesson_id.is_not(None))).all())
    mastery = curriculum_state(session)
    for offset in range(7):
        day = start + timedelta(days=offset)
        if day < today:
            continue
        existing = session.exec(select(StudyTask).where(StudyTask.scheduled_date == day, StudyTask.status != "cancelled")).all()
        available = max(0, prefs.available_minutes[offset] - sum(t.planned_minutes for t in existing))
        english_target = round(prefs.available_minutes[offset] * prefs.english_percent / 100)
        english = min(available, max(0, english_target - sum(t.planned_minutes for t in existing if t.subject == "english")))
        for subject, budget in (("english", english), ("python", available - english)):
            remaining = budget
            eligible = [(l, c, m) for l, c, m in catalogue if m.subject == subject and l.id not in completed | assigned and mastery[l.id]["unlocked"]]
            # At most two new lessons per subject/day; reserve time for retrieval practice.
            added = 0
            for lesson, content, meta in eligible:
                if added == 2 or content.duration_minutes > remaining:
                    break
                session.add(StudyTask(id=str(uuid4()), plan_week=start, scheduled_date=day, original_date=day,
                    subject=subject, kind="lesson", title=lesson.title, lesson_id=lesson.id,
                    instructions=f"Изучи теорию и выполни все задания. Тема: {meta.topic}. После урока отметь фактически потраченное время.",
                    planned_minutes=content.duration_minutes, created_at=clock.now()))
                assigned.add(lesson.id)
                remaining -= content.duration_minutes
                added += 1
            block = 0
            while remaining > 0:
                minutes = min(25, remaining)
                # Do not schedule tiny isolated tasks when rounding leaves a few minutes.
                if remaining - minutes in range(1, 5):
                    minutes = remaining
                review = next(iter(sorted(((l, c, m) for l, c, m in catalogue if m.subject == subject and l.id in completed),
                    key=lambda row: (mastery[row[0].id]["best_percent"], row[2].position))), None)
                title, instructions = PRACTICE[subject][(offset + block) % len(PRACTICE[subject])]
                session.add(StudyTask(id=str(uuid4()), plan_week=start, scheduled_date=day, original_date=day,
                    subject=subject, kind="review" if review and block == 0 else "practice",
                    title=f"Повторение: {review[0].title}" if review and block == 0 else title,
                    instructions="Повтори теорию и задания знакомого урока. Затем отметь время самостоятельного повторения." if review and block == 0 else instructions,
                    lesson_id=review[0].id if review and block == 0 else None,
                    planned_minutes=minutes, created_at=clock.now()))
                remaining -= minutes
                block += 1
    session.flush()


def get_task(session, task_id):
    task = session.get(StudyTask, str(task_id))
    if task is None:
        raise HTTPException(404, "Задание не найдено")
    return task


def complete(session, task, minutes):
    if task.status == "completed":
        return  # Idempotent completion: preserve the first recorded minutes.
    if task.status != "pending":
        raise HTTPException(409, "Это задание отменено при обновлении плана")
    if task.scheduled_date > clock.local_day():
        raise HTTPException(409, "Сначала перенеси будущее задание на сегодня")
    if task.kind == "lesson":
        run = session.exec(select(LessonRun).where(LessonRun.lesson_id == task.lesson_id,
            LessonRun.completed_at >= task.created_at).order_by(LessonRun.completed_at.desc())).first()
        if not run:
            raise HTTPException(409, "Сначала заверши все упражнения этого урока")
        task.completed_run_id = run.id
    task.status = "completed"
    task.actual_minutes = minutes
    task.completed_at = clock.now()
    session.add(task)


def reschedule(session, task, day):
    if task.status != "pending":
        raise HTTPException(409, "Переносить можно только невыполненные задания")
    if not clock.local_day() <= day <= clock.local_day() + timedelta(days=365):
        raise HTTPException(422, "Выбери сегодня или дату в пределах следующего года")
    if day == task.scheduled_date:
        return
    tasks = session.exec(select(StudyTask).where(StudyTask.scheduled_date == day, StudyTask.status != "cancelled")).all()
    used = sum(t.planned_minutes for t in tasks)
    if used + task.planned_minutes > settings(session).available_minutes[day.weekday()]:
        raise HTTPException(409, "На этот день не хватает времени. Измени доступное время или выбери другой день.")
    session.add(TaskMove(task_id=task.id, from_date=task.scheduled_date, to_date=day, moved_at=clock.now()))
    task.scheduled_date = day
    session.add(task)


def adapt(session, start):
    """Reschedule missed work before adding new work; never rewrite completions."""
    today = clock.local_day()
    if start != monday(start) or not monday(today) <= start <= monday(today)+timedelta(weeks=52):
        raise HTTPException(422, "Выбери текущую или будущую неделю в пределах года")
    overdue = session.exec(select(StudyTask).where(StudyTask.status == "pending", StudyTask.scheduled_date < today)
        .order_by(StudyTask.scheduled_date, StudyTask.created_at).limit(100)).all()
    if not overdue:
        return dict(week=week_read(session, start), moved=0, remaining_overdue=0)
    active = set(session.exec(select(LessonRun.lesson_id).where(LessonRun.completed_at.is_(None))).all())
    moved_before = set(session.exec(select(TaskMove.task_id)).all())
    # Retain manual moves, incoming tasks, completed work, and lessons already started.
    for task in session.exec(select(StudyTask).where(StudyTask.plan_week == start, StudyTask.status == "pending",
            StudyTask.scheduled_date >= max(today,start), StudyTask.scheduled_date < start+timedelta(days=7))).all():
        if task.id not in moved_before and task.lesson_id not in active:
            task.status = "cancelled"
            session.add(task)
    session.flush()
    prefs = settings(session)
    moved = 0
    for task in overdue:
        for offset in range(7):
            day = start + timedelta(days=offset)
            if day < today:
                continue
            occupied = session.exec(select(StudyTask).where(StudyTask.scheduled_date == day, StudyTask.status != "cancelled")).all()
            if sum(t.planned_minutes for t in occupied) + task.planned_minutes <= prefs.available_minutes[offset]:
                reschedule(session, task, day)
                session.flush()
                moved += 1
                break
    generate(session, start, fill_existing=True)
    remaining = len(session.exec(select(StudyTask).where(StudyTask.status == "pending", StudyTask.scheduled_date < today)).all())
    return dict(week=week_read(session, start), moved=moved, remaining_overdue=remaining)
