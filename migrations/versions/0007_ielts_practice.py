"""Original IELTS practice and durable drafts. No official band estimation."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "0007_ielts_practice"
down_revision = "0006_english_levels"
branch_labels = depends_on = None


def upgrade():
    tests = op.create_table("ieltstest", sa.Column("id", sa.String, primary_key=True),
        sa.Column("section", sa.String, nullable=False), sa.Column("title", sa.String, nullable=False),
        sa.Column("instructions", sa.String, nullable=False), sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("content", sa.JSON, nullable=False))
    op.create_index("ix_ieltstest_section", "ieltstest", ["section"])
    op.create_table("ieltsrun", sa.Column("id", sa.String, primary_key=True),
        sa.Column("test_id", sa.String, sa.ForeignKey("ieltstest.id"), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("submitted_at", sa.DateTime), sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("answers", sa.JSON, nullable=False), sa.Column("text", sa.String, nullable=False),
        sa.Column("mode", sa.String, nullable=False), sa.Column("result", sa.JSON))
    op.create_index("ix_ieltsrun_test_id", "ieltsrun", ["test_id"])
    data = json.loads((Path(__file__).parents[1]/"data/ielts-practice-v1.json").read_text(encoding="utf8"))
    op.get_bind().execute(tests.insert(), data)


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
