"""Persistent weekly planner; only additive schema changes."""
from alembic import op
import sqlalchemy as sa

revision = "0003_planner"
down_revision = "0002_learning"
branch_labels = depends_on = None


def upgrade():
    op.create_table("lessonmeta",
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), primary_key=True),
        sa.Column("subject", sa.String, nullable=False), sa.Column("topic", sa.String, nullable=False),
        sa.Column("position", sa.Integer, nullable=False))
    op.create_index("ix_lessonmeta_subject", "lessonmeta", ["subject"])
    op.create_table("studysettings", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("available_minutes", sa.JSON, nullable=False),
        sa.Column("daily_goal_minutes", sa.Integer, nullable=False),
        sa.Column("weekly_goal_minutes", sa.Integer, nullable=False),
        sa.Column("reminder_enabled", sa.Boolean, nullable=False),
        sa.Column("reminder_time", sa.String, nullable=False),
        sa.Column("timezone", sa.String, nullable=False))
    op.create_table("planweek", sa.Column("week_start", sa.Date, primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False), sa.Column("created_at", sa.DateTime, nullable=False))
    op.create_table("studytask", sa.Column("id", sa.String, primary_key=True),
        sa.Column("plan_week", sa.Date, sa.ForeignKey("planweek.week_start"), nullable=False),
        sa.Column("scheduled_date", sa.Date, nullable=False), sa.Column("original_date", sa.Date, nullable=False),
        sa.Column("subject", sa.String, nullable=False), sa.Column("kind", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False), sa.Column("instructions", sa.String, nullable=False),
        sa.Column("planned_minutes", sa.Integer, nullable=False),
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id")),
        sa.Column("status", sa.String, nullable=False), sa.Column("actual_minutes", sa.Integer),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("completed_run_id", sa.String, sa.ForeignKey("lessonrun.id")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("planned_minutes > 0", name="ck_task_planned"),
        sa.CheckConstraint("actual_minutes IS NULL OR actual_minutes BETWEEN 1 AND 480", name="ck_task_actual"),
        sa.CheckConstraint("status IN ('pending', 'completed', 'cancelled')", name="ck_task_status"))
    for column in ("plan_week", "scheduled_date"):
        op.create_index(f"ix_studytask_{column}", "studytask", [column])
    op.create_table("taskmove", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.String, sa.ForeignKey("studytask.id"), nullable=False),
        sa.Column("from_date", sa.Date, nullable=False), sa.Column("to_date", sa.Date, nullable=False),
        sa.Column("moved_at", sa.DateTime, nullable=False))
    op.create_index("ix_taskmove_task_id", "taskmove", ["task_id"])
    bind = op.get_bind()
    bind.execute(sa.text("INSERT INTO lessonmeta (lesson_id, subject, topic, position) SELECT lesson_id, 'english', 'Daily Routines', 1 FROM lessoncontent"))
    settings = sa.table("studysettings", sa.column("id"), sa.column("available_minutes", sa.JSON),
        sa.column("daily_goal_minutes"), sa.column("weekly_goal_minutes"), sa.column("reminder_enabled"),
        sa.column("reminder_time"), sa.column("timezone"))
    bind.execute(settings.insert().values(id=1, available_minutes=[90,90,90,90,90,180,180],
        daily_goal_minutes=30, weekly_goal_minutes=210, reminder_enabled=False, reminder_time="19:00", timezone="Asia/Almaty"))


def downgrade():
    raise RuntimeError("Restore a verified backup explicitly; destructive downgrade disabled.")
