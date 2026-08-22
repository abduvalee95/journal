"""students.telegram_id must be a 64-bit integer

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-22

The initial schema declared telegram_id as Integer. On SQLite that is harmless:
its INTEGER storage class is variable-width, so a 10-digit id round-trips
fine and every test passed. On Postgres, Integer is int4 -- maximum
2,147,483,647 -- and Telegram ids crossed that years ago. The single teacher
this app is built for already has an id near 7e9, so the *first* /start on a
Postgres deployment would have raised NumericValueOutOfRange and no student
could ever register.

Found while porting from SQLite to Postgres; the two databases disagreeing
about what Integer means is exactly the kind of thing that only surfaces at
the moment of the move.

Only telegram_id changes. The other Integer columns are surrogate keys, grades
(1-5) and counters, all far inside int4.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode so this also runs on SQLite, where ALTER COLUMN TYPE does not
    # exist and the table has to be rebuilt. On Postgres it degrades to a
    # plain ALTER TABLE ... TYPE BIGINT.
    with op.batch_alter_table('students') as batch_op:
        batch_op.alter_column(
            'telegram_id',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Narrowing back to int4 will fail on Postgres if any stored id exceeds
    # 2^31, which is the normal case. That is correct: the downgrade is not
    # safely reversible once real ids are present.
    with op.batch_alter_table('students') as batch_op:
        batch_op.alter_column(
            'telegram_id',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
