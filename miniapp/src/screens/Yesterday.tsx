import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { formatDateUz, yesterdayIso } from "../lib/date";
import { sameAttendance, toStudentRows, type LessonData, type StudentData } from "../lib/types";
import {
  setMainButton,
  hideMainButton,
  showMainButtonLoading,
  hideMainButtonLoading,
  haptic,
} from "../lib/telegram";
import StudentRow from "../components/StudentRow";

export default function Yesterday() {
  // Resolved once per mount: recomputing it on every render would change the
  // query key if the screen happened to be open across local midnight.
  const date = useMemo(() => yesterdayIso(), []);

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["lesson", date],
    queryFn: () => apiFetch<LessonData>(`/api/lessons?date=${date}`),
  });

  // As on the Today screen, the server rows stay in the query cache and React
  // state holds only the teacher's overrides. That also makes "what changed"
  // a plain comparison against the rows the server last returned, with no
  // separate baseline to keep in sync.
  const [edits, setEdits] = useState<ReadonlyMap<number, StudentData>>(new Map());
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saving = useRef(false);

  const serverRows = useMemo(() => (data ? toStudentRows(data) : []), [data]);
  const students = useMemo(
    () => serverRows.map((row) => edits.get(row.id) ?? row),
    [serverRows, edits],
  );

  const changed = useMemo(
    () =>
      students.filter((s, i) => {
        const original = serverRows[i];
        // PATCH /api/attendance/{id} can only update a row that exists. A
        // student who joined the group after this lesson was saved has none and
        // the endpoint would 404, so they are excluded here and shown read-only
        // rather than silently dropped on save the way the task brief's
        // `if (s.att_id)` guard did.
        return s.att_id !== null && !sameAttendance(s, original);
      }),
    [students, serverRows],
  );

  const uncorrectable = students.filter((s) => s.att_id === null);

  const saveRef = useRef<() => void>(() => {});

  const handleSave = async () => {
    if (saving.current || changed.length === 0) return;
    saving.current = true;
    setSaveError(null);
    showMainButtonLoading();
    haptic();
    try {
      await Promise.all(
        changed.map((s) =>
          apiFetch(`/api/attendance/${s.att_id}`, {
            method: "PATCH",
            body: JSON.stringify({
              student_id: s.id,
              status: s.status,
              grade: s.status === "absent" ? null : s.grade,
              note_public: s.note_public.trim() || null,
            }),
          }),
        ),
      );
      // No /confirm call here, and that is the whole point of this screen:
      // corrections must not queue a second round of student messages.
      setSaved(true);
      setEdits(new Map());
      // Re-read so the rows the diff compares against are the ones now stored,
      // which both confirms the write landed and empties `changed`.
      await refetch();
      hideMainButton();
    } catch {
      setSaveError("Тузатишлар сақланмади. Қайтадан уриниб кўринг.");
      hideMainButtonLoading();
    } finally {
      saving.current = false;
    }
  };
  saveRef.current = handleSave;

  useEffect(() => {
    // Nothing to save until something is actually different, so the button
    // only appears once the teacher has changed a row.
    if (!data?.lesson || changed.length === 0) {
      hideMainButton();
      return;
    }
    setMainButton("Сақлаш (жим)", () => saveRef.current());
    return hideMainButton;
  }, [data?.lesson, changed.length]);

  const handleStudentChange = (updated: StudentData) => {
    setSaved(false);
    setEdits((prev) => new Map(prev).set(updated.id, updated));
  };

  if (isPending) return <div className="p-4 text-gray-400">Юкланмоқда...</div>;
  if (isError) {
    return <div className="p-4 text-red-500">Маълумот юкланмади. Қайта очинг.</div>;
  }
  if (!data.group || !data.lesson) {
    return <div className="p-4 text-gray-500">Кеча дарс бўлмаган.</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 pb-20">
      <h1 className="mb-1 text-lg font-semibold">Кеча — {data.group.name}</h1>
      <p className="mb-3 text-xs text-gray-400">{formatDateUz(data.lesson.date)}</p>
      <p className="mb-4 text-xs text-orange-500">⚠️ Тузатиш ўқувчиларга хабар юбормайди</p>

      {saved && (
        <div className="mb-4 rounded-lg bg-green-100 p-3 text-sm text-green-700">
          ✅ Тузатишлар сақланди.
        </div>
      )}
      {saveError && (
        <div role="alert" className="mb-4 rounded-lg bg-red-100 p-3 text-sm text-red-700">
          {saveError}
        </div>
      )}

      {students.map((s) => (
        <StudentRow
          key={s.id}
          student={s}
          disabled={s.att_id === null}
          onChange={handleStudentChange}
        />
      ))}

      {uncorrectable.length > 0 && (
        <p className="mt-2 text-xs text-gray-500">
          {uncorrectable.map((s) => s.full_name).join(", ")} — бу дарсда ёзув йўқ, тузатиб
          бўлмайди.
        </p>
      )}
    </div>
  );
}
