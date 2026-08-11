"""Builds the per-student attendance report sent to Telegram.

Privacy is enforced structurally: build_report only ever reads lesson_date,
topic, summary_public, homework (from the lesson), status, grade, note_public
(from the attendance), and name (from the group). It never reads
lesson.raw_note or attendance.note_private -- those are teacher-only fields
and simply are not part of this function's vocabulary.
"""
from app.utils.localtime import format_date_uz

STATUS_LINE = {
    "present": "✅ Келдингиз",
    "absent":  "❌ Келмадингиз",
    "late":    "🕐 Кеч келдингиз",
}


def build_report(lesson, attendance, group) -> str:
    parts = [f"📚 {group.name} — {format_date_uz(lesson.lesson_date)}"]
    if lesson.topic:
        parts.append(f"Мавзу: {lesson.topic}")
    if lesson.summary_public:
        parts.append(f"\n{lesson.summary_public}")
    parts.append("\n---")
    parts.append(STATUS_LINE.get(attendance.status, attendance.status))
    if attendance.grade is not None:
        parts.append(f"⭐ Баҳо: {attendance.grade}/5")
    if attendance.note_public:
        parts.append(f"💬 {attendance.note_public}")
    if lesson.homework:
        parts.append(f"\n📝 Уй вазифаси: {lesson.homework}")
    return "\n".join(parts)
