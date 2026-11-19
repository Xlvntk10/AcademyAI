from alembic import context
from app.database.db import make_engine


def run(connection=None):
    context.configure(connection=connection, dialect_name="postgresql",
                      version_table_schema="academy_migrations", transactional_ddl=True)
    with context.begin_transaction():
        # Keep the revision outside tenant tables and outside PostgREST.
        context.execute("CREATE SCHEMA IF NOT EXISTS academy_migrations")
        context.execute("REVOKE ALL ON SCHEMA academy_migrations FROM PUBLIC")
        context.run_migrations()


if context.is_offline_mode():
    run()
else:
    engine = make_engine(context.config.attributes["database_url"])
    try:
        with engine.begin() as connection:
            run(connection)
    finally:
        engine.dispose()
