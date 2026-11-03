import re
from fastapi import HTTPException
from app.database.models import IeltsRun, IeltsTest
from app.services import clock
from app.services.learning import normalize


def get_test(session, test_id):
    test = session.get(IeltsTest, test_id)
    if not test:
        raise HTTPException(404, "Тренировка не найдена")
    return test


def get_run(session, run_id):
    run = session.get(IeltsRun, str(run_id))
    if not run:
        raise HTTPException(404, "Работа не найдена")
    return run


def test_read(test):
    content = {**test.content}
    if "questions" in content:
        content["questions"] = [{key: q[key] for key in ("id", "prompt", "options")} for q in content["questions"]]
    return dict(id=test.id, section=test.section, title=test.title, instructions=test.instructions,
        duration_seconds=test.duration_seconds, content=content)


def run_read(session, run):
    test = get_test(session, run.test_id)
    return dict(id=run.id, test_id=run.test_id, title=test.title, section=test.section,
        started_at=clock.as_utc(run.started_at), updated_at=clock.as_utc(run.updated_at),
        submitted_at=clock.as_utc(run.submitted_at) if run.submitted_at else None,
        revision=run.revision, answers=run.answers, text=run.text, mode=run.mode, result=run.result)


def grade(test, run):
    elapsed = max(0, int((clock.now() - clock.as_utc(run.started_at)).total_seconds()))
    base = dict(elapsed_seconds=elapsed, over_time=elapsed > test.duration_seconds,
        mode=run.mode, notice="Учебная практика. Это не официальный IELTS band score.")
    questions = test.content.get("questions", [])
    if questions:
        answers = []
        for q in questions:
            answer = run.answers.get(q["id"], "")
            correct = normalize(answer) in {normalize(v) for v in [q["answer"], *q.get("accepted", [])]}
            answers.append(dict(id=q["id"], prompt=q["prompt"], answer=answer, is_correct=correct,
                correct_answer=q["answer"], explanation=q["explanation"]))
        score = sum(a["is_correct"] for a in answers)
        return dict(**base, score=score, total=len(questions), percent=round(score/len(questions)*100,1), answers=answers,
            recommendations=["Вернись к объяснениям ошибок и найди доказательство ответа в тексте или записи." if score < len(questions) else "Повтори навык на другом тексте: один результат не подтверждает готовность к экзамену."])
    words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:[.,]\d+)*", run.text)
    paragraphs = [p for p in re.split(r"\n\s*\n", run.text.strip()) if p.strip()]
    minimum = test.content.get("min_words", 0)
    advice = list(test.content.get("guide", []))
    if minimum and len(words) < minimum:
        advice.insert(0, f"Объём: {len(words)} слов по простому счётчику; ориентир задания — не менее {minimum}. Развивай аргументы, а не добавляй пустые фразы.")
    if test.section == "writing" and len(paragraphs) < 2:
        advice.insert(0, "Раздели разные мысли на абзацы пустой строкой. Число абзацев само по себе не оценивает качество.")
    advice.append("Грамматика, содержание и произношение автоматически не оцениваются. Используй критерии для самопроверки или обратной связи преподавателя.")
    return dict(**base, score=None, word_count=len(words), paragraphs=len(paragraphs),
        criteria=test.content.get("criteria", []), recommendations=advice)


def save(session, run, payload, submit=False):
    test = get_test(session, run.test_id)
    questions = {q["id"]: q for q in test.content.get("questions", [])}
    if set(payload.answers) - set(questions):
        raise HTTPException(422, "Ответ содержит неизвестный вопрос")
    for key, answer in payload.answers.items():
        options = questions[key]["options"]
        if options and answer and answer not in options:
            raise HTTPException(422, "Выберите предложенный вариант")
    if test.section not in ("listening", "speaking") and payload.mode != "text":
        raise HTTPException(422, "Для этой работы нужен текстовый режим")
    same = run.answers == payload.answers and run.text == payload.text and run.mode == payload.mode
    if run.submitted_at:
        if submit and same:
            return run
        raise HTTPException(409, "Работа уже завершена. Начните новую тренировку.")
    if run.revision != payload.revision:
        if same and not submit:
            return run  # Retried successful draft save.
        raise HTTPException(409, "Работа изменена в другой вкладке. Скопируйте свой текст и обновите страницу.")
    if submit and test.section in ("writing", "speaking") and payload.mode == "text" and not payload.text.strip():
        raise HTTPException(422, "Напишите ответ перед завершением")
    run.answers = payload.answers
    run.text = payload.text
    run.mode = payload.mode
    run.updated_at = clock.now()
    run.revision += 1
    if submit:
        run.submitted_at = clock.now()
        run.result = grade(test, run)
    session.add(run)
    session.commit()
    return run
