"""review gate, delivery uniqueness, one active group per weekday

Revision ID: a1b2c3d4e5f6
Revises: 8056176ffc04
Create Date: 2026-08-14

Three schema changes, all of them backstops for guarantees the application
code cannot make on its own:

1. lessons.summary_reviewed / lessons.manual_edit_at -- summary_public is
   written verbatim from model output and sent to the whole class, so confirm
   needs to know whether a human ever saw it; and the pipeline needs to know
   whether the teacher has typed since it started.
2. UNIQUE(lesson_id, student_id) on outbox -- two concurrent confirms both
   passed the status check and both inserted a full set of rows, so every
   student received their report twice.
3. groups: UNIQUE(weekday, is_active) permitted only one *inactive* group per
   weekday too, so archiving a second Monday group failed. Replaced with a
   partial unique index over active rows only.

SQLite cannot drop a table-level constraint in place, so the groups table is
rebuilt with batch_alter_table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8056176ffc04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The initial migration created UNIQUE(weekday, is_active) unnamed, and SQLite
# cannot drop an unnamed constraint. Describing the table here -- with the
# constraint named -- gives batch mode a definition to rebuild from, so the
# recreated table simply does not carry it.
_GROUPS_BEFORE = sa.Table(
    'groups',
    sa.MetaData(),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('weekday', 'is_active', name='uq_groups_weekday_is_active'),
)


def upgrade() -> None:
    op.add_column(
        'lessons',
        sa.Column('summary_reviewed', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column('lessons', sa.Column('manual_edit_at', sa.Text(), nullable=True))

    # Any lesson already confirmed had its reports built and sent under the old
    # behaviour; marking those reviewed keeps the gate from retroactively
    # blocking history.
    op.execute("UPDATE lessons SET summary_reviewed = 1 WHERE status = 'saved'")

    # Collapse any duplicates a pre-constraint double-confirm produced, keeping
    # the earliest row per (lesson, student).
    op.execute("""
        DELETE FROM outbox
        WHERE id NOT IN (
            SELECT MIN(id) FROM outbox GROUP BY lesson_id, student_id
        )
    """)
    with op.batch_alter_table('outbox') as batch_op:
        batch_op.create_unique_constraint('uq_outbox_lesson_student', ['lesson_id', 'student_id'])

    # The initial migration declared UNIQUE(weekday, is_active) without a name,
    # and the two databases fill that blank differently. SQLite keeps it
    # anonymous, so it can only be removed by rebuilding the table from a
    # definition that names it -- which is what copy_from is for, the name
    # there being a label, never SQL. Postgres invents its own name
    # ("groups_weekday_is_active_key"), and batch mode on Postgres emits a real
    # ALTER TABLE ... DROP CONSTRAINT, so the invented name is the only one
    # that works. Asking the catalogue avoids depending on either convention.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""
            DO $$
            DECLARE cname text;
            BEGIN
                SELECT conname INTO cname
                FROM pg_constraint
                WHERE conrelid = 'groups'::regclass AND contype = 'u';
                IF cname IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE groups DROP CONSTRAINT %I', cname);
                END IF;
            END $$;
        """)
    else:
        with op.batch_alter_table('groups', copy_from=_GROUPS_BEFORE) as batch_op:
            batch_op.drop_constraint('uq_groups_weekday_is_active', type_='unique')
    op.create_index(
        'uq_groups_active_weekday',
        'groups',
        ['weekday'],
        unique=True,
        sqlite_where=sa.text('is_active = 1'),
        postgresql_where=sa.text('is_active = 1'),
    )


def downgrade() -> None:
    op.drop_index('uq_groups_active_weekday', table_name='groups')
    with op.batch_alter_table('groups') as batch_op:
        batch_op.create_unique_constraint('uq_groups_weekday_is_active', ['weekday', 'is_active'])

    with op.batch_alter_table('outbox') as batch_op:
        batch_op.drop_constraint('uq_outbox_lesson_student', type_='unique')

    op.drop_column('lessons', 'manual_edit_at')
    op.drop_column('lessons', 'summary_reviewed')
