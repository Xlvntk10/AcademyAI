"""Adopt the original schema after validating it, or initialize an empty DB."""
from alembic import op
import sqlalchemy as sa

revision = "0001_legacy"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    metadata = sa.MetaData()
    sa.Table("skill", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False))
    sa.Table("lesson", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("level", sa.String, nullable=False))
    sa.Table("exercise", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lesson_id", sa.Integer, sa.ForeignKey("lesson.id"), nullable=False),
        sa.Column("question", sa.String, nullable=False),
        sa.Column("correct_answer", sa.String, nullable=False),
        sa.Column("points", sa.Integer, nullable=False))
    sa.Table("attempt", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("exercise_id", sa.Integer, sa.ForeignKey("exercise.id"), nullable=False),
        sa.Column("answer", sa.String, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("earned_points", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False))
    for table, column, unique in [("skill", "name", True), ("lesson", "skill_id", False),
        ("lesson", "title", False), ("exercise", "lesson_id", False), ("attempt", "exercise_id", False)]:
        sa.Index(f"ix_{table}_{column}", metadata.tables[table].c[column], unique=unique)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names()) - {"alembic_version"}
    if existing:
        if existing != set(metadata.tables):
            raise RuntimeError("Unexpected legacy tables; migration stopped without changes.")
        for name, table in metadata.tables.items():
            columns = inspector.get_columns(name)
            expected = [(c.name, str(c.type), c.nullable) for c in table.columns]
            actual = [(c["name"], str(c["type"]), c["nullable"]) for c in columns]
            if actual != expected or inspector.get_pk_constraint(name)["constrained_columns"] != ["id"]:
                raise RuntimeError(f"Unexpected legacy schema: {name}")
            expected_fk = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
            actual_fk = {(fk["constrained_columns"][0], fk["referred_table"]) for fk in inspector.get_foreign_keys(name)}
            if expected_fk != actual_fk:
                raise RuntimeError(f"Unexpected foreign keys: {name}")
            actual_indexes = {(tuple(i["column_names"]), bool(i["unique"])) for i in inspector.get_indexes(name)}
            if any((tuple(c.name for c in idx.columns), idx.unique) not in actual_indexes for idx in table.indexes):
                raise RuntimeError(f"Missing legacy index: {name}")
    else:
        metadata.create_all(bind)


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled. Restore a verified backup explicitly.")
