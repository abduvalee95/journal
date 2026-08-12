export type AttStatus = "present" | "absent" | "late";

/** Shape of GET /api/today and GET /api/lessons?date=... (app/api/lessons.py). */
export interface LessonData {
  group: { id: number; name: string } | null;
  lesson: {
    id: number;
    date: string;
    topic: string | null;
    homework: string | null;
    summary_public: string | null;
    status: string;
    /** A voice note has been received for this lesson, so an AI draft is on
     * its way (or already landed). Drives the VoiceStatus spinner. */
    has_audio: boolean;
  } | null;
  students: { id: number; full_name: string }[];
  attendance: {
    id: number;
    student_id: number;
    status: AttStatus;
    grade: number | null;
    note_public: string | null;
  }[];
}

/** One student row as the form holds it: server data flattened per student,
 * with nulls turned into the empty strings the inputs need. */
export interface StudentData {
  id: number;
  full_name: string;
  status: AttStatus;
  grade: number | null;
  note_public: string;
  att_id: number | null;
}

export function toStudentRows(data: LessonData): StudentData[] {
  const byStudent = new Map(data.attendance.map((a) => [a.student_id, a]));
  return data.students.map((s) => {
    const att = byStudent.get(s.id);
    return {
      id: s.id,
      full_name: s.full_name,
      status: att?.status ?? "present",
      grade: att?.grade ?? null,
      note_public: att?.note_public ?? "",
      att_id: att?.id ?? null,
    };
  });
}
