import asyncio

from sqlalchemy import select

from app.db.models import Group
from app.db.session import AsyncSessionLocal

GROUPS = [
    {"name": "Beginners A",         "weekday": 1, "start_time": "09:00"},
    {"name": "Elementary B",        "weekday": 2, "start_time": "11:00"},
    {"name": "Pre-Intermediate C",  "weekday": 3, "start_time": "14:00"},
    {"name": "Intermediate D",      "weekday": 4, "start_time": "16:00"},
    {"name": "Upper-Intermediate E","weekday": 5, "start_time": "18:00"},
    {"name": "Advanced F",          "weekday": 6, "start_time": "10:00"},
]

async def seed():
    """Insert the six groups, once. Run *after* `alembic upgrade head`.

    Deliberately does not create the schema. It used to call
    `Base.metadata.create_all`, which meant running it first built the tables
    without stamping an Alembic version -- and every later migration then
    failed against a database Alembic believed was empty.
    """
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(Group.id).limit(1))).first()
        if existing is not None:
            print("Groups already seeded, skipping")
            return
        for g in GROUPS:
            session.add(Group(**g))
        await session.commit()
    print("Seeded 6 groups")

if __name__ == "__main__":
    asyncio.run(seed())
