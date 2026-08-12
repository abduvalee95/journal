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
    <div className="mb-2 rounded-xl border bg-white p-3 shadow-sm">
      <div className="mb-2 text-sm font-medium">{student.full_name}</div>

      <div className="mb-2 flex gap-1" role="group" aria-label={`${student.full_name} — давомат`}>
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            aria-pressed={student.status === s}
            onClick={() => setStatus(s)}
            className={`rounded-full border px-2 py-1 text-xs transition-colors disabled:opacity-50 ${
              student.status === s
                ? "border-blue-500 bg-blue-500 text-white"
                : "border-gray-200 bg-gray-100 text-gray-600"
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      {student.status !== "absent" && (
        <div className="mb-2 flex gap-1" role="group" aria-label={`${student.full_name} — баҳо`}>
          {GRADES.map((g) => (
            <button
              key={g}
              type="button"
              disabled={disabled}
              aria-pressed={student.grade === g}
              onClick={() => toggleGrade(g)}
              className={`h-8 w-8 rounded-full border text-sm disabled:opacity-50 ${
                student.grade === g
                  ? "border-yellow-400 bg-yellow-400 text-white"
                  : "border-gray-200 bg-gray-100 text-gray-500"
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
        onChange={(e) => set({ note_public: e.target.value })}
        className="w-full rounded border bg-gray-50 px-2 py-1 text-xs disabled:opacity-50"
      />
    </div>
  );
}
