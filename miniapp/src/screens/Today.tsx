import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, SessionExpiredError } from "../lib/api";
import { formatDateUz } from "../lib/date";
import { clearDraft, loadDraft, saveDraft } from "../lib/draft";
import { sameAttendance, toStudentRows, type LessonData, type StudentData } from "../lib/types";
import {
  setMainButton,
  hideMainButton,
  showMainButtonLoading,
  hideMainButtonLoading,
  setClosingConfirmation,
  haptic,
} from "../lib/telegram";
import StudentRow from "../components/StudentRow";
import DraftReview from "../components/DraftReview";
import VoiceStatus from "../components/VoiceStatus";

export default function Today() {
  const queryClient = useQueryClient();
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
  const [summaryEdit, setSummaryEdit] = useState<string | null>(null);

  const [savedNow, setSavedNow] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [watchedLessonId, setWatchedLessonId] = useState<number | null>(null);
  const [draftWaiting, setDraftWaiting] = useState(false);

  // Guards against a second MainButton tap while the first save is in flight:
  // showProgress() spins the button but does not stop it firing again, and a
  // double POST /confirm would be wasted work.
  const saving = useRef(false);

  // Derived rather than mirrored: an effect copying lesson.status into state
  // would leave one commit where the data has arrived but `saved` is still
  // false, and the MainButton effect would flash "Сақлаш" on a saved lesson.
  const saved = savedNow || data?.lesson?.status === "saved";
  const lessonId = data?.lesson?.id ?? null;

  const serverRows = useMemo(() => (data ? toStudentRows(data) : []), [data]);
  const students = useMemo(
    () => serverRows.map((row) => edits.get(row.id) ?? row),
    [serverRows, edits],
  );
  const topic = topicEdit ?? data?.lesson?.topic ?? "";
  const homework = homeworkEdit ?? data?.lesson?.homework ?? "";
  const summary = summaryEdit ?? data?.lesson?.summary_public ?? "";
  const summaryReviewed = summaryEdit !== null || (data?.lesson?.summary_reviewed ?? true);
  const hasSummary = summary.trim().length > 0;

  // Nothing has been typed yet, so an incoming AI draft is free to replace what
  // is on screen.
  const pristine =
    edits.size === 0 && topicEdit === null && homeworkEdit === null && summaryEdit === null;

  // Restore anything typed before the screen was last unmounted (a tab switch)
  // or before the app was closed and reopened.
  const restoredFor = useRef<number | null>(null);
  useEffect(() => {
    if (lessonId === null || restoredFor.current === lessonId) return;
    restoredFor.current = lessonId;
    const stored = loadDraft(lessonId);
    if (!stored) return;
    setEdits(new Map(stored.edits));
    setTopicEdit(stored.topicEdit);
    setHomeworkEdit(stored.homeworkEdit);
    setSummaryEdit(stored.summaryEdit);
  }, [lessonId]);

  useEffect(() => {
    if (lessonId === null || saved) return;
    if (pristine) clearDraft(lessonId);
    else saveDraft(lessonId, { edits: [...edits], topicEdit, homeworkEdit, summaryEdit });
  }, [lessonId, saved, pristine, edits, topicEdit, homeworkEdit, summaryEdit]);

  // Telegram closes on a swipe-down and the form is in memory; warn while there
  // is something to lose.
  useEffect(() => {
    setClosingConfirmation(!pristine && !saved);
    return () => setClosingConfirmation(false);
  }, [pristine, saved]);

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
  // when the draft lands, their input wins -- but the draft is announced rather
  // than silently dropped, so they can choose to load it.
  const handleDraftReady = () => {
    if (pristine) void refetch();
    else setDraftWaiting(true);
  };

  const loadAiDraft = () => {
    setEdits(new Map());
    setTopicEdit(null);
    setHomeworkEdit(null);
    setSummaryEdit(null);
    setDraftWaiting(false);
    clearDraft(lessonId);
    void refetch();
  };

  // The MainButton handler is registered once per screen but must read the
  // *current* form state when tapped. Telegram keeps the exact function it was
  // given, so re-registering on every keystroke is wasteful and re-registering
  // only on [data, saved] would save whatever the form held at first render and
  // silently drop every edit. A ref holding the latest save closure is the fix.
  const saveRef = useRef<() => void>(() => {});

  const handleSave = async () => {
    const lesson = data?.lesson;
    if (!lesson || saved || saving.current) return;
    if (hasSummary && !summaryReviewed) {
      setSaveError("Аввал умумий хулосани кўриб чиқинг.");
      return;
    }
    saving.current = true;
    setSaveError(null);
    showMainButtonLoading();
    haptic();
    try {
      if (summaryEdit !== null) {
        await apiFetch(`/api/lessons/${lesson.id}`, {
          method: "PATCH",
          body: JSON.stringify({ summary_public: summaryEdit }),
        });
      }
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
      clearDraft(lesson.id);
      // Without this the cache still says "draft", so tabbing away and back
      // brought the save button and an editable form straight back -- which
      // reads as the save having failed.
      queryClient.setQueryData<LessonData>(["today"], (prev) =>
        prev?.lesson ? { ...prev, lesson: { ...prev.lesson, status: "saved" } } : prev,
      );
      hideMainButton();
    } catch (err: unknown) {
      setSaveError(
        err instanceof SessionExpiredError
          ? "Сессия тугади. Иловани ёпиб, қайта очинг — ёзганларингиз сақланиб қолди."
          : "Сақлаб бўлмади. Қайтадан уриниб кўринг.",
      );
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
    const original = serverRows.find((row) => row.id === updated.id);
    setEdits((prev) => {
      // Re-selecting the value already on screen is not an edit. Recording it
      // anyway made the form non-pristine on a single idle tap, which was
      // enough to make an arriving AI draft be discarded.
      if (original && sameAttendance(original, updated)) {
        if (!prev.has(updated.id)) return prev;
        const next = new Map(prev);
        next.delete(updated.id);
        return next;
      }
      return new Map(prev).set(updated.id, updated);
    });
  };

  if (isPending) return <div className="p-4 text-tg-hint">Юкланмоқда...</div>;
  // isError is true even when `data` is present, if a *background* refetch
  // failed (react-query's isRefetchError). Replacing a filled-in form with
  // "reopen the app" was how a network blip destroyed the teacher's work.
  if (isError && !data) {
    return (
      <div className="p-4">
        <p className="mb-3 text-red-500">Маълумот юкланмади.</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="min-h-11 rounded-lg bg-tg-button px-4 text-tg-buttonText"
        >
          Қайта уриниш
        </button>
      </div>
    );
  }
  if (!data) return <div className="p-4 text-tg-hint">Юкланмоқда...</div>;
  if (!data.group || !data.lesson) {
    return <div className="p-4 text-tg-hint">Бугун дарс йўқ.</div>;
  }

  return (
    <div className="min-h-screen bg-tg-secondaryBg p-4 pb-20">
      <h1 className="mb-1 text-lg font-semibold">{data.group.name}</h1>
      <p className="mb-4 text-xs text-tg-hint">{formatDateUz(data.lesson.date)}</p>

      {isError && (
        <div role="alert" className="mb-4 rounded-lg bg-orange-100 p-3 text-sm text-orange-800">
          Янгилаб бўлмади — ёзганларингиз жойида.{" "}
          <button type="button" className="underline" onClick={() => void refetch()}>
            Қайта уриниш
          </button>
        </div>
      )}

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

      {draftWaiting && !saved && (
        <div role="status" className="mb-4 rounded-lg bg-blue-50 p-3 text-sm text-blue-700">
          AI қоралама тайёр. Ёзганларингиз ўрнига юклайсизми?{" "}
          <button type="button" className="font-medium underline" onClick={loadAiDraft}>
            Юклаш
          </button>
        </div>
      )}

      {watchedLessonId !== null && !saved && (
        <VoiceStatus lessonId={watchedLessonId} onDraftReady={handleDraftReady} />
      )}

      <DraftReview
        topic={topic}
        homework={homework}
        summary={summary}
        summaryReviewed={summaryReviewed}
        disabled={saved}
        onTopicChange={setTopicEdit}
        onHomeworkChange={setHomeworkEdit}
        onSummaryChange={setSummaryEdit}
      />

      {students.length === 0 ? (
        <p className="text-sm text-tg-hint">
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
