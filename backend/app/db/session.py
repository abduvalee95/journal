from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        """Pragmas SQLite does not apply by default but this schema depends on.

        foreign_keys: off by default, which makes every FOREIGN KEY in the
            migration decorative and turns `ON DELETE CASCADE` on
            attendance.lesson_id into a no-op.
        journal_mode=WAL: the default (`delete`) blocks readers while a writer
            holds the file. The outbox worker writes every 30s alongside Mini
            App requests, so readers would stall on it.
        busy_timeout: wait for a contended write instead of raising
            "database is locked" straight into a 500.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
