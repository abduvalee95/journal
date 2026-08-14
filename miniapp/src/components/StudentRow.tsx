import type { AttStatus, StudentData } from "../lib/types";

interface Props {
  student: StudentData;
  disabled?: boolean;
  onChange: (updated: StudentData) => void;
}

const STATUS_LABELS: Record<AttStatus, string> = {
  present: "✅ Келди",
  absent: "❌ Келмади",
  late: "🕐 Кеч",
};

const STATUSES: AttStatus[] = ["present", "absent", "late"];
const GRADES = [1, 2, 3, 4, 5];

/** Note length matches the backend's cap; an oversized note pushed the
 * student's report past Telegram's 4096-character limit, so sendMessage failed
 * and after three retries the student silently received nothing. */
const MAX_NOTE = 400;

export default function StudentRow({ student, disabled = false, onChange }: Props) {
  const set = (patch: Partial<StudentData>) => onChange({ ...student, ...patch });

  const setStatus = (status: AttStatus) => {
    // Clearing the grade here is not cosmetic: the picker is merely hidden for
    // an absent student, so a grade set before the toggle would still be sent
    // and build_report() prints "⭐ Баҳо" for any non-null grade regardless of
    // status -- an absent student would get graded in their own report.
    set(status === "absent" ? { status, grade: null } : { status });
  };

  const toggleGrade = (grade: number) => {
    set({ grade: student.grade === grade ? null : grade });
  };

  return (
    <div className="mb-2 rounded-xl border border-tg-hint/20 bg-tg-bg p-3 shadow-sm">
      <div className="mb-2 text-sm font-medium text-tg-text">{student.full_name}</div>

      {/* 44px minimum touch targets: the teacher works through fifteen students
          on a phone straight after a lesson. */}
      <div className="mb-2 flex gap-2" role="group" aria-label={`${student.full_name} — давомат`}>
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            aria-pressed={student.status === s}
            onClick={() => setStatus(s)}
            className={`min-h-11 flex-1 rounded-full border px-3 text-sm transition-colors disabled:opacity-50 ${
              student.status === s
                ? "border-blue-500 bg-blue-500 text-white"
                : "border-tg-hint/30 bg-tg-secondaryBg text-tg-text"
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {student.status !== "absent" && (
        <div className="mb-2 flex gap-2" role="group" aria-label={`${student.full_name} — баҳо`}>
          {GRADES.map((g) => (
            <button
              key={g}
              type="button"
              disabled={disabled}
              aria-pressed={student.grade === g}
              onClick={() => toggleGrade(g)}
              className={`min-h-11 min-w-11 flex-1 rounded-full border text-base disabled:opacity-50 ${
                student.grade === g
                  ? "border-yellow-400 bg-yellow-400 text-white"
                  : "border-tg-hint/30 bg-tg-secondaryBg text-tg-text"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      )}

      <input
        type="text"
        disabled={disabled}
        aria-label={`${student.full_name} — изоҳ`}
        placeholder="Изоҳ (ихтиёрий)"
        value={student.note_public}
        maxLength={MAX_NOTE}
        onChange={(e) => set({ note_public: e.target.value })}
        /* text-base (16px) is also what stops iOS zooming the page on focus --
           the viewport tag used to suppress that by banning zoom entirely. */
        className="min-h-11 w-full rounded border border-tg-hint/30 bg-tg-secondaryBg px-2 text-base text-tg-text placeholder:text-tg-hint disabled:opacity-50"
      />
    </div>
  );
}
