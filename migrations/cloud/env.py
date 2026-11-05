from alembic import context
from app.database.db import make_engine

engine = make_engine(context.config.attributes["database_url"])
with engine.begin() as connection:
    # Keep the cloud revision outside the tenant tables and outside PostgREST.
    connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS academy_migrations")
    connection.exec_driver_sql("REVOKE ALL ON SCHEMA academy_migrations FROM PUBLIC")
    context.configure(connection=connection, version_table_schema="academy_migrations", transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
