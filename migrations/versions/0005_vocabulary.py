"""Optional vocabulary review. Existing records and scores remain untouched."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0005_vocabulary"
down_revision = "0004_academies"
branch_labels = depends_on = None


def upgrade():
    card = op.create_table("vocabularycard", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), nullable=False),
        sa.Column("term", sa.String, unique=True, nullable=False),
        sa.Column("translation", sa.String, nullable=False), sa.Column("example", sa.String, nullable=False))
    op.create_index("ix_vocabularycard_lesson_id", "vocabularycard", ["lesson_id"])
    op.create_table("vocabularyprogress",
        sa.Column("card_id", sa.Integer, sa.ForeignKey("vocabularycard.id"), primary_key=True),
        sa.Column("box", sa.Integer, nullable=False), sa.Column("due_on", sa.Date, nullable=False),
        sa.Column("added_at", sa.DateTime, nullable=False), sa.Column("review_count", sa.Integer, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False), sa.CheckConstraint("box BETWEEN 0 AND 5", name="ck_vocab_box"))
    op.create_table("vocabularyreview", sa.Column("id", sa.String, primary_key=True),
        sa.Column("card_id", sa.Integer, sa.ForeignKey("vocabularycard.id"), nullable=False),
        sa.Column("answer", sa.String, nullable=False), sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("reviewed_at", sa.DateTime, nullable=False), sa.Column("due_on", sa.Date, nullable=False),
        sa.Column("box", sa.Integer, nullable=False))
    op.create_index("ix_vocabularyreview_card_id", "vocabularyreview", ["card_id"])
    bind = op.get_bind()
    lessons = dict(bind.execute(sa.text("SELECT slug, lesson_id FROM lessoncontent")).all())
    data = json.loads((Path(__file__).resolve().parents[1] / "data/vocabulary-a2-v1.json").read_text(encoding="utf8"))
    for item in data:
        bind.execute(card.insert().values(lesson_id=lessons[item["slug"]], term=item["term"],
            translation=item["translation"], example=item["example"]))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
