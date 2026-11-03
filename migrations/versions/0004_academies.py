"""Publish curated A2 and beginner Python lessons with exact code answers."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0004_academies"
down_revision = "0003_planner"
branch_labels = depends_on = None


def upgrade():
    op.add_column("exercisecontent", sa.Column("case_sensitive", sa.Boolean, nullable=False, server_default=sa.false()))
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=bind)
    tables = meta.tables
    skill = tables["skill"]
    python_skill = bind.execute(sa.select(skill.c.id).where(skill.c.name == "Python")).scalar_one_or_none()
    if python_skill is None:
        python_skill = bind.execute(skill.insert().values(name="Python", description="Основы программирования на Python")).inserted_primary_key[0]
    reading = bind.execute(sa.select(skill.c.id).where(skill.c.name == "Reading")).scalar_one()
    for filename in ("english-a2-v1.json", "python-basics-v1.json"):
        lessons = json.loads((Path(__file__).parents[1] / "data" / filename).read_text(encoding="utf-8"))
        for data in lessons:
            is_python = data["subject"] == "python"
            lesson_id = bind.execute(tables["lesson"].insert().values(skill_id=python_skill if is_python else reading,
                title=data["title"], level=data["level"])).inserted_primary_key[0]
            bind.execute(tables["lessoncontent"].insert().values(lesson_id=lesson_id, slug=data["slug"],
                summary=data["summary"], duration_minutes=data["duration_minutes"], version=1, theory=data["theory"]))
            bind.execute(tables["lessonmeta"].insert().values(lesson_id=lesson_id, subject=data["subject"], topic=data["topic"], position=data["position"]))
            for position, item in enumerate(data["exercises"], 1):
                exercise_id = bind.execute(tables["exercise"].insert().values(lesson_id=lesson_id,
                    question=item["question"], correct_answer=item["correct_answer"], points=10)).inserted_primary_key[0]
                bind.execute(tables["exercisecontent"].insert().values(exercise_id=exercise_id, position=position,
                    kind=item["kind"], options=item.get("options", []), explanation=item["explanation"],
                    accepted_answers=item.get("accepted_answers", []), case_sensitive=is_python))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
