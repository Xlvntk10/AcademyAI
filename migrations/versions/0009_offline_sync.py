"""Durable offline receipts, database identity and reminder preferences."""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "0009_offline_sync"
down_revision = "0008_learning_horizon"
branch_labels = depends_on = None


def upgrade():
    op.create_table("syncidentity", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("server_id", sa.String, nullable=False))
    op.bulk_insert(sa.table("syncidentity", sa.column("id", sa.Integer), sa.column("server_id", sa.String)),
                   [{"id": 1, "server_id": str(uuid4())}])
    op.create_table("offlinereceipt",
        sa.Column("id", sa.String, sa.ForeignKey("lessonrun.id"), primary_key=True),
        sa.Column("payload_hash", sa.String, nullable=False),
        sa.Column("client_started_at", sa.DateTime, nullable=False),
        sa.Column("client_completed_at", sa.DateTime, nullable=False),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("result", sa.JSON, nullable=False))
    op.add_column("studysettings", sa.Column("reminder_days", sa.JSON, nullable=False, server_default="[0,1,2,3,4,5,6]"))
    op.add_column("studysettings", sa.Column("masters_target_date", sa.Date, nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
