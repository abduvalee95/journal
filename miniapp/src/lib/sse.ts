import { ApiError, apiUrl, getToken } from "./api";

export interface LessonEvent {
  event: string;
}

/** Read the lesson's SSE stream until it ends or `signal` aborts.
 *
 * Deliberately not `EventSource`: that API cannot set an Authorization header,
 * and the alternative the task brief suggests -- passing the JWT as `?token=`
 * -- writes a live teacher credential into access logs, browser history and
 * Referer headers. `fetch` + a ReadableStream reader keeps it in the header
 * and needs no backend change, since GET /api/lessons/{id}/stream already sits
 * behind the ordinary `require_teacher` Bearer dependency.
 *
 * The backend closes the stream itself after `draft_ready` or its 90s timeout
 * (app/api/lessons.py `_event_stream`), so there is no reconnect logic here --
 * one open stream per mounted component, ended by the server or the abort.
 */
export async function streamLessonEvents(
  lessonId: number,
  onEvent: (event: LessonEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/api/lessons/${lessonId}/stream`), {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    signal,
  });
  if (!response.ok) {
    throw new ApiError(response.status, `SSE ${response.status}: lesson ${lessonId}`);
  }
  if (!response.body) throw new ApiError(0, "SSE response had no body");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line; a chunk can hold several frames
      // or split one down the middle, so only complete frames are consumed.
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        emitFrame(buffer.slice(0, boundary), onEvent);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}

function emitFrame(frame: string, onEvent: (event: LessonEvent) => void): void {
  for (const line of frame.split("\n")) {
    if (!line.startsWith("data:")) continue;
    try {
      const parsed = JSON.parse(line.slice(5).trim()) as LessonEvent;
      if (parsed && typeof parsed.event === "string") onEvent(parsed);
    } catch {
      // A malformed frame is not worth tearing the stream down for: the next
      // one may well be the draft_ready the teacher is waiting on.
    }
  }
}
