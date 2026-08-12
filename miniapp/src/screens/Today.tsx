import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { formatDateUz } from "../lib/date";
import { toStudentRows, type LessonData, type StudentData } from "../lib/types";
import {
  setMainButton,
  hideMainButton,
  showMainButtonLoading,
  hideMainButtonLoading,
  haptic,
} from "../lib/telegram";
import StudentRow from "../components/StudentRow";
import DraftReview from "../components/DraftReview";
import VoiceStatus from "../components/VoiceStatus";

export default function Today() {
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["today"],
    queryFn: () => apiFetch<LessonData>("/api/today"),
  });

  // Server state is never copied into React state. The form holds only what the
  // teacher has overridden, layered on top of the query data, so there is no
  // effect to run and therefore no render where the lesson header is on screen
  // but the roster underneath it is still empty.
  const [edits, setEdits] = useState<ReadonlyMap<number, StudentData>>(new Map());
  const [topicEdit, setTopicEdit] = useState<string | null>(null);
  const [homeworkEdit, setHomeworkEdit] = useState<string | null>(null);

  const [savedNow, setSavedNow] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [watchedLessonId, setWatchedLessonId] = useState<number | null>(null);

  // Guards against a second MainButton tap while the first save is in flight:
  // showProgress() spins the button but does not stop it firing again, and a
  // double POST /confirm would be wasted work.
  const saving = useRef(false);

  // Derived rather than mirrored: an effect copying lesson.status into state
  // would leave one commit where the data has arrived but `saved` is still
  // false, and the MainButton effect would flash "Сақлаш" on a saved lesson.
  const saved = savedNow || data?.lesson?.status === "saved";

  const serverRows = useMemo(() => (data ? toStudentRows(data) : []), [data]);
  const students = useMemo(
    () => serverRows.map((row) => edits.get(row.id) ?? row),
    [serverRows, edits],
  );
  const topic = topicEdit ?? data?.lesson?.topic ?? "";
  const homework = homeworkEdit ?? data?.lesson?.homework ?? "";

  // Nothing has been typed yet, so an incoming AI draft is free to replace what
  // is on screen.
  const pristine = edits.size === 0 && topicEdit === null && homeworkEdit === null;

  useEffect(() => {
    const lesson = data?.lesson;
    // has_audio means the bot stored a voice note for this lesson, so a draft
    // really is being produced -- without it the spinner would appear on every
    // empty lesson the teacher opens for plain manual entry and then "fail".
    if (!lesson || lesson.status !== "draft" || !lesson.has_audio) return;
    if (data.attendance.length > 0) return;
    setWatchedLessonId(lesson.id);
  }, [data]);

  // Only a pristine form is replaced. If the teacher has already started typing
  // when the draft lands, their input wins and the draft is simply ignored.
  const handleDraftReady = () => {
    if (pristine) void refetch();
  };

  // The MainButton handler is registered once per screen but must read the
  // *current* form state when tapped. Telegram keeps the exact function it was
  // given, so re-registering on every keystroke is wasteful and re-registering
  // only on [data, saved] (as the task brief does) would save whatever the form
  // held at first render and silently drop every edit. A ref holding the latest
  // save closure is the fix.
  const saveRef = useRef<() => void>(() => {});

  const handleSave = async () => {
    const lesson = data?.lesson;
    if (!lesson || saved || saving.current) return;
    saving.current = true;
    setSaveError(null);
    showMainButtonLoading();
    haptic();
    try {
      await apiFetch(`/api/lessons/${lesson.id}/attendance`, {
        method: "PUT",
        body: JSON.stringify({
          topic,
          homework,
          items: students.map((s) => ({
            student_id: s.id,
            status: s.status,
            grade: s.status === "absent" ? null : s.grade,
            note_public: s.note_public.trim() || null,
          })),
        }),
      });
      // Separate call on purpose: PUT only stores the attendance, POST /confirm
      // is what flips the lesson to "saved" and queues the student messages.
      await apiFetch(`/api/lessons/${lesson.id}/confirm`, { method: "POST" });
      setSavedNow(true);
      hideMainButton();
    } catch {
      setSaveError("Сақлаб бўлмади. Қайтадан уриниб кўринг.");
      hideMainButtonLoading();
    } finally {
      saving.current = false;
    }
  };
  saveRef.current = handleSave;

  useEffect(() => {
    if (!data?.lesson || saved) {
      hideMainButton();
      return;
    }
    setMainButton("Сақлаш", () => saveRef.current());
    return hideMainButton;
  }, [data?.lesson, saved]);

  const handleStudentChange = (updated: StudentData) => {
    setEdits((prev) => new Map(prev).set(updated.id, updated));
  };

  if (isPending) return <div className="p-4 text-gray-400">Юкланмоқда...</div>;
  if (isError) {
    return <div className="p-4 text-red-500">Маълумот юкланмади. Қайта очинг.</div>;
  }
  if (!data.group || !data.lesson) {
    return <div className="p-4 text-gray-500">Бугун дарс йўқ.</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 pb-20">
      <h1 className="mb-1 text-lg font-semibold">{data.group.name}</h1>
      <p className="mb-4 text-xs text-gray-400">{formatDateUz(data.lesson.date)}</p>

      {saved && (
        <div className="mb-4 rounded-lg bg-green-100 p-3 text-sm text-green-700">
          ✅ Сақланди. Ўқувчиларга хабар юборилмоқда.
        </div>
      )}
      {saveError && (
        <div role="alert" className="mb-4 rounded-lg bg-red-100 p-3 text-sm text-red-700">
          {saveError}
        </div>
      )}

      {watchedLessonId !== null && !saved && (
        <VoiceStatus lessonId={watchedLessonId} onDraftReady={handleDraftReady} />
      )}

      <DraftReview
        topic={topic}
        homework={homework}
        disabled={saved}
        onTopicChange={setTopicEdit}
        onHomeworkChange={setHomeworkEdit}
      />

      {students.length === 0 ? (
        <p className="text-sm text-gray-500">
          Бу гуруҳда ҳали ўқувчи йўқ. Улар ботга /start юборсин.
        </p>
      ) : (
        students.map((s) => (
          <StudentRow key={s.id} student={s} disabled={saved} onChange={handleStudentChange} />
        ))
      )}
    </div>
  );
}
