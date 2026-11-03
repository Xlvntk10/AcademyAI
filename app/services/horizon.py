"""Calendar capacity and recommendations derived from saved evidence."""
from calendar import monthrange
from datetime import date, timedelta
from sqlmodel import select
from app.database.models import Lesson, LessonContent, LessonMeta, LessonRun, StudyTask, IeltsRun, IeltsTest
from app.services import clock
from app.services.mastery import curriculum_state
from app.services.planner import settings, task_read


def roadmap(session):
    today = clock.local_day()
    prefs = settings(session)
    state = curriculum_state(session)
    active = set(session.exec(select(LessonRun.lesson_id).where(LessonRun.completed_at.is_(None))).all())
    attempted = set(session.exec(select(LessonRun.lesson_id)).all())
    topics = []
    for lesson, content, meta in session.exec(select(Lesson, LessonContent, LessonMeta).join(LessonContent)
            .join(LessonMeta, LessonMeta.lesson_id == Lesson.id).order_by(LessonMeta.subject, LessonMeta.position)).all():
        value = state[lesson.id]
        topics.append(dict(slug=content.slug, title=lesson.title, subject=meta.subject, level=lesson.level,
            best_percent=value["best_percent"], attempted=lesson.id in attempted, status="mastered" if value["mastered"] else "in_progress" if lesson.id in active else "open" if value["unlocked"] else "locked"))
    completed_tasks = session.exec(select(StudyTask).where(StudyTask.status == "completed")).all()
    monthly_done = sum(t.actual_minutes or 0 for t in completed_tasks if t.completed_at and
        clock.local_day(t.completed_at).strftime('%Y-%m') == today.strftime('%Y-%m') and clock.local_day(t.completed_at) <= today)
    phases = [level for level in ('A2','B1','B2') if any(t['level']==level and t['status']!='mastered' for t in topics)] + ['IELTS']
    months = []
    cursor = today.replace(day=1)
    end = date.fromisoformat(prefs.target_month+'-01') if prefs.target_month else None
    while end and cursor <= end:
        last = cursor.replace(day=monthrange(cursor.year,cursor.month)[1])
        day = max(cursor, today)
        available = 0
        english = 0
        while day <= last:
            minutes = prefs.available_minutes[day.weekday()]
            available += minutes
            english += round(minutes*prefs.english_percent/100)
            day += timedelta(days=1)
        months.append(dict(month=cursor.strftime('%Y-%m'), available_minutes=available, english_minutes=english,
            python_minutes=available-english, goal_minutes=prefs.monthly_goal_minutes))
        cursor = last + timedelta(days=1)
    for index, month in enumerate(months):
        month['focus'] = phases[min(len(phases)-1, index*len(phases)//len(months))] if len(months)>1 else 'Текущие пробелы и IELTS'
    recommendations = []
    candidates = sorted((t for t in topics if t['status'] in ('open','in_progress')),
        key=lambda t:(not t['attempted'], t['status']!='in_progress', t['best_percent']))
    for topic in candidates[:4]:
        recommendations.append(dict(title=topic['title'], route='lesson/'+topic['slug'],
            reason=f"Лучший результат {topic['best_percent']}%: повтори ошибки до 80%." if topic['attempted'] else "Доступная следующая тема. Сначала теория, затем объективная практика."))
    latest = {}
    for run, test in session.exec(select(IeltsRun, IeltsTest).join(IeltsTest).where(IeltsRun.submitted_at.is_not(None))
            .order_by(IeltsRun.submitted_at.desc())).all():
        latest.setdefault(test.section, (run, test))
    ielts = []
    for section in ('listening','reading','writing','speaking'):
        pair = latest.get(section)
        row = dict(section=section, latest_percent=None, mode=None, submitted_at=None)
        if pair:
            run, test = pair
            row.update(latest_percent=(run.result or {}).get('percent'), mode=run.mode, submitted_at=clock.as_utc(run.submitted_at))
            if row['latest_percent'] is not None and row['latest_percent'] < 80:
                recommendations.append(dict(title=test.title, route='ielts/run/'+run.id,
                    reason=f"Последняя тренировка: {row['latest_percent']}%. Разбери сохранённые ошибки; это не band score."))
        ielts.append(row)
    return dict(today=today, target_month=prefs.target_month, english_percent=prefs.english_percent,
        monthly_goal=dict(target_minutes=prefs.monthly_goal_minutes, completed_minutes=monthly_done, reached=monthly_done >= prefs.monthly_goal_minutes),
        months=months, topics=topics, recommendations=recommendations, ielts=ielts,
        mastered_count=sum(t['status']=='mastered' for t in topics), total_topics=len(topics),
        notice="Показан охват тем библиотеки, а не готовность к IELTS 6.5. Месячные фокусы — ориентиры; темп зависит от результатов.")
