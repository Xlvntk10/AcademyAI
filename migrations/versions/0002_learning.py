"""Add lesson content and runs; preserve every legacy record."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0002_learning"
down_revision = "0001_legacy"
branch_labels = depends_on = None


def upgrade():
    op.create_table("lessoncontent",
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), primary_key=True),
        sa.Column("slug", sa.String, nullable=False),
        sa.Column("summary", sa.String, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("theory", sa.JSON, nullable=False))
    op.create_index("ix_lessoncontent_slug", "lessoncontent", ["slug"], unique=True)
    op.create_table("exercisecontent",
        sa.Column("exercise_id", sa.Integer, sa.ForeignKey("exercise.id"), primary_key=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.Column("explanation", sa.String, nullable=False),
        sa.Column("accepted_answers", sa.JSON, nullable=False))
    op.create_table("lessonrun",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), nullable=False),
        sa.Column("content_version", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime))
    op.create_index("ix_lessonrun_lesson_id", "lessonrun", ["lesson_id"])
    op.create_table("runanswer",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("lessonrun.id"), nullable=False),
        sa.Column("exercise_id", sa.Integer, sa.ForeignKey("exercise.id"), nullable=False),
        sa.Column("attempt_id", sa.Integer, sa.ForeignKey("attempt.id"), nullable=False, unique=True),
        sa.UniqueConstraint("run_id", "exercise_id", name="uq_run_exercise"))
    op.create_index("ix_runanswer_run_id", "runanswer", ["run_id"])

    data = json.loads((Path(__file__).parents[1] / "data/a2-daily-routine-v1.json").read_text(encoding="utf-8"))
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=bind)
    skill, lesson, exercise = (meta.tables[n] for n in ("skill", "lesson", "exercise"))
    skill_id = bind.execute(sa.select(skill.c.id).where(skill.c.name == "Reading")).scalar_one_or_none()
    if skill_id is None:
        skill_id = bind.execute(skill.insert().values(name="Reading", description="Чтение и анализ текста")).inserted_primary_key[0]
    lesson_id = bind.execute(lesson.insert().values(skill_id=skill_id, title=data["title"], level="A2")).inserted_primary_key[0]
    bind.execute(meta.tables["lessoncontent"].insert().values(lesson_id=lesson_id, slug=data["slug"],
        summary=data["summary"], duration_minutes=12, version=1, theory=data["theory"]))
    for position, item in enumerate(data["exercises"], 1):
        exercise_id = bind.execute(exercise.insert().values(lesson_id=lesson_id, question=item["question"],
            correct_answer=item["correct_answer"], points=10)).inserted_primary_key[0]
        bind.execute(meta.tables["exercisecontent"].insert().values(exercise_id=exercise_id, position=position,
            kind=item["kind"], options=item.get("options", []), explanation=item["explanation"],
            accepted_answers=item.get("accepted_answers", [])))


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled. Restore a verified backup explicitly.")
