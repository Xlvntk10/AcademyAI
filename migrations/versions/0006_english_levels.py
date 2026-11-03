"""Add B1/B2 and prerequisites without modifying any existing content."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0006_english_levels"
down_revision = "0005_vocabulary"
branch_labels = depends_on = None


def upgrade():
    gate = op.create_table("lessonprerequisite", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), nullable=False),
        sa.Column("prerequisite_id", sa.Integer, sa.ForeignKey("lesson.id"), nullable=False),
        sa.UniqueConstraint("lesson_id", "prerequisite_id", name="uq_lesson_prerequisite"))
    op.create_index("ix_lessonprerequisite_lesson_id", "lessonprerequisite", ["lesson_id"])
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=bind)
    tables = meta.tables
    reading = bind.execute(sa.select(tables["skill"].c.id).where(tables["skill"].c.name == "Reading")).scalar_one()
    prerequisites = list(bind.execute(sa.text("SELECT l.id FROM lesson l JOIN lessonmeta m ON l.id=m.lesson_id WHERE l.level='A2' AND m.subject='english'")).scalars())
    for level in ("b1", "b2"):
        data = json.loads((Path(__file__).parents[1]/"data"/f"english-{level}-v1.json").read_text(encoding="utf8"))
        for item in data:
            lesson_id = bind.execute(tables["lesson"].insert().values(skill_id=reading, title=item["title"], level=item["level"])).inserted_primary_key[0]
            bind.execute(tables["lessoncontent"].insert().values(lesson_id=lesson_id, slug=item["slug"], summary=item["summary"], duration_minutes=item["duration_minutes"], version=1, theory=item["theory"]))
            bind.execute(tables["lessonmeta"].insert().values(lesson_id=lesson_id, subject="english", topic=item["topic"], position=item["position"]))
            for prerequisite_id in prerequisites:
                bind.execute(gate.insert().values(lesson_id=lesson_id, prerequisite_id=prerequisite_id))
            prerequisites = [lesson_id]
            for position, exercise in enumerate(item["exercises"], 1):
                exercise_id = bind.execute(tables["exercise"].insert().values(lesson_id=lesson_id, question=exercise["question"], correct_answer=exercise["correct_answer"], points=10)).inserted_primary_key[0]
                bind.execute(tables["exercisecontent"].insert().values(exercise_id=exercise_id, position=position, kind=exercise["kind"], options=exercise.get("options",[]), explanation=exercise["explanation"], accepted_answers=exercise.get("accepted_answers",[]), case_sensitive=False))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
