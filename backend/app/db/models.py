from sqlalchemy import (Column, Integer, Text, CheckConstraint,
                        UniqueConstraint, ForeignKey, Index)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Group(Base):
    __tablename__ = "groups"
    id         = Column(Integer, primary_key=True)
    name       = Column(Text, nullable=False)
    weekday    = Column(Integer, nullable=False)   # 1=Mon..6=Sat
    start_time = Column(Text)
    is_active  = Column(Integer, nullable=False, default=1)

# One *active* group per weekday. UNIQUE(weekday, is_active) also allowed only
# one *inactive* group per weekday, so archiving a second Monday group raised
# IntegrityError and a seventh group could never be added at all.
Index(
    "uq_groups_active_weekday",
    Group.weekday,
    unique=True,
    sqlite_where=Group.is_active == 1,
    postgresql_where=Group.is_active == 1,
)

class Student(Base):
    __tablename__ = "students"
    id          = Column(Integer, primary_key=True)
    group_id    = Column(Integer, ForeignKey("groups.id"), nullable=False)
    full_name   = Column(Text, nullable=False)
    telegram_id = Column(Integer, unique=True, nullable=False)
    joined_at   = Column(Text, nullable=False)
    is_active   = Column(Integer, nullable=False, default=1)

Index("idx_students_group", Student.group_id, Student.is_active)

class Lesson(Base):
    __tablename__ = "lessons"
    id             = Column(Integer, primary_key=True)
    group_id       = Column(Integer, ForeignKey("groups.id"), nullable=False)
    lesson_date    = Column(Text, nullable=False)   # YYYY-MM-DD Asia/Bishkek
    topic          = Column(Text)
    raw_note       = Column(Text)                   # NEVER sent to students
    audio_file_id  = Column(Text)
    summary_public = Column(Text)
    homework       = Column(Text)
    status         = Column(Text, nullable=False, default="draft")  # draft|saved
    saved_at       = Column(Text)
    created_at     = Column(Text, nullable=False)

    # summary_public is the one field written straight from model output and
    # sent to the whole class. 0 means "as the AI wrote it"; the teacher has to
    # see and accept it before confirm will build any reports from it.
    summary_reviewed = Column(Integer, nullable=False, default=0)

    # When the teacher last wrote to this lesson by hand. The AI pipeline
    # refuses to overwrite anything edited after it started, so a draft landing
    # mid-entry cannot silently replace what the teacher typed.
    manual_edit_at = Column(Text)

    __table_args__ = (UniqueConstraint("group_id", "lesson_date"),)

class Attendance(Base):
    __tablename__ = "attendance"
    id           = Column(Integer, primary_key=True)
    lesson_id    = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    student_id   = Column(Integer, ForeignKey("students.id"), nullable=False)
    status       = Column(Text, nullable=False)   # present|absent|late
    grade        = Column(Integer)                # 1..5 or NULL
    note_public  = Column(Text)
    note_private = Column(Text)
    notified_at  = Column(Text)
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_id"),
        CheckConstraint("grade IS NULL OR (grade BETWEEN 1 AND 5)"),
    )

class Outbox(Base):
    __tablename__ = "outbox"
    id         = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    lesson_id  = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    text       = Column(Text, nullable=False)
    status     = Column(Text, nullable=False, default="pending")  # pending|sent|failed
    attempts   = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    created_at = Column(Text, nullable=False)
    sent_at    = Column(Text)
    # One report per student per lesson. The database is the backstop for
    # duplicate delivery: application-level checks cannot be trusted across
    # two concurrent confirms.
    __table_args__ = (UniqueConstraint("lesson_id", "student_id"),)

Index("idx_outbox_pending", Outbox.status, Outbox.created_at)

class AiJob(Base):
    __tablename__ = "ai_jobs"
    id          = Column(Integer, primary_key=True)
    lesson_id   = Column(Integer, ForeignKey("lessons.id"))
    stage       = Column(Text)       # asr|llm
    status      = Column(Text)       # running|done|error
    duration_ms = Column(Integer)
    error       = Column(Text)
    created_at  = Column(Text, nullable=False)
