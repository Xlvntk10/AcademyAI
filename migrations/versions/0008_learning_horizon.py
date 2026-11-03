"""Configurable study balance and a learner-selected IELTS month."""
from alembic import op
import sqlalchemy as sa

revision = "0008_learning_horizon"
down_revision = "0007_ielts_practice"
branch_labels = depends_on = None


def upgrade():
    op.add_column("studysettings", sa.Column("english_percent", sa.Integer, nullable=False, server_default="65"))
    op.add_column("studysettings", sa.Column("monthly_goal_minutes", sa.Integer, nullable=False, server_default="900"))
    op.add_column("studysettings", sa.Column("target_month", sa.String, nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
