import { useEffect, useRef, useState } from "react";
import { streamLessonEvents } from "../lib/sse";

interface Props {
  lessonId: number;
  /** Fired once, when the AI draft has landed in the database. */
  onDraftReady: () => void;
}

type Status = "waiting" | "done" | "gave-up";

export default function VoiceStatus({ lessonId, onDraftReady }: Props) {
  const [status, setStatus] = useState<Status>("waiting");

  // Read through a ref so a new inline callback from the parent's next render
  // does not reopen the stream mid-flight.
  const onDraftReadyRef = useRef(onDraftReady);
  onDraftReadyRef.current = onDraftReady;

  useEffect(() => {
    const controller = new AbortController();
    let settled = false;

    const finish = (next: Status) => {
      if (settled) return;
      settled = true;
      setStatus(next);
      if (next === "done") onDraftReadyRef.current();
    };

    streamLessonEvents(
      lessonId,
      (event) => {
        if (event.event === "draft_ready") finish("done");
        else if (event.event === "timeout") finish("gave-up");
      },
      controller.signal,
    )
      // The stream ending without a draft_ready also counts as giving up: the
      // server closes it after its own 90s timeout, and a dropped connection or
      // a rejected request looks the same from here. Either way the teacher
      // should stop waiting and enter the lesson by hand.
      .then(() => finish("gave-up"))
      .catch(() => {
        if (!controller.signal.aborted) finish("gave-up");
      });

    return () => controller.abort();
  }, [lessonId]);

  if (status === "done") return null;
  if (status === "gave-up") {
    return (
      <div role="status" className="mb-3 text-xs text-orange-500">
        ⚠️ AI қоралама келмади — қўлда киритинг
      </div>
    );
  }
  return (
    <div role="status" className="mb-3 flex items-center gap-2 text-xs text-blue-500">
      <span className="animate-spin">⏳</span> AI қоралама тайёрланмоқда...
    </div>
  );
}
