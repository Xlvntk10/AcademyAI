"""Online migrations only; SQLite DDL and data run in one real transaction."""
from alembic import context
from sqlalchemy import event
from app.database.db import DATABASE_URL, make_engine


def run(connection):
    context.configure(connection=connection, transactional_ddl=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


supplied = context.config.attributes.get("connection")
if supplied is not None:
    run(supplied)
else:
    if context.is_offline_mode():
        raise RuntimeError("Use online migrations against a verified database copy.")
    engine = make_engine(context.config.attributes.get("database_url", DATABASE_URL))

    @event.listens_for(engine, "connect")
    def manual_transactions(dbapi_connection, _):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    with engine.connect() as connection:
        run(connection)
    engine.dispose()
