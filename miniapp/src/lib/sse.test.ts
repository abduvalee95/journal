import { afterEach, describe, expect, it, vi } from "vitest";
import { streamLessonEvents, type LessonEvent } from "./sse";
import { authenticate, clearToken } from "./api";

/** Build a Response whose body streams the given chunks, one per read. */
function sseResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return { ok: status < 400, status, body } as unknown as Response;
}

async function collect(chunks: string[]): Promise<LessonEvent[]> {
  vi.stubGlobal("fetch", vi.fn(async () => sseResponse(chunks)));
  const events: LessonEvent[] = [];
  await streamLessonEvents(7, (e) => events.push(e), new AbortController().signal);
  return events;
}

afterEach(() => {
  clearToken();
  vi.unstubAllGlobals();
});

describe("streamLessonEvents", () => {
  it("sends the JWT in the Authorization header, never in the URL", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith("/api/auth/telegram")) {
        return { ok: true, status: 200, json: async () => ({ access_token: "jwt-123" }) } as Response;
      }
      return sseResponse(['data: {"event": "draft_ready"}\n\n']);
    });
    vi.stubGlobal("fetch", fetchMock);

    await authenticate("init");
    await streamLessonEvents(7, () => {}, new AbortController().signal);

    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/lessons/7/stream");
    expect(url).not.toContain("jwt-123");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer jwt-123");
  });

  it("parses a draft_ready frame", async () => {
    expect(await collect(['data: {"event": "draft_ready"}\n\n'])).toEqual([
      { event: "draft_ready" },
    ]);
  });

  it("parses a timeout frame", async () => {
    expect(await collect(['data: {"event": "timeout"}\n\n'])).toEqual([{ event: "timeout" }]);
  });

  it("reassembles a frame split across chunks", async () => {
    expect(await collect(['data: {"eve', 'nt": "draft_r', 'eady"}\n\n'])).toEqual([
      { event: "draft_ready" },
    ]);
  });

  it("emits both frames when one chunk carries two", async () => {
    const events = await collect(['data: {"event": "ping"}\n\ndata: {"event": "draft_ready"}\n\n']);
    expect(events).toEqual([{ event: "ping" }, { event: "draft_ready" }]);
  });

  it("ignores a trailing partial frame with no blank-line terminator", async () => {
    expect(await collect(['data: {"event": "draft_ready"}'])).toEqual([]);
  });

  it("skips a malformed frame and keeps reading", async () => {
    const events = await collect(['data: not json\n\ndata: {"event": "draft_ready"}\n\n']);
    expect(events).toEqual([{ event: "draft_ready" }]);
  });

  it("ignores JSON that is not a lesson event", async () => {
    expect(await collect(["data: 42\n\n", 'data: {"nope": 1}\n\n'])).toEqual([]);
  });

  it("throws ApiError when the endpoint rejects the request", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => sseResponse([], 401)));
    await expect(
      streamLessonEvents(7, () => {}, new AbortController().signal),
    ).rejects.toMatchObject({ name: "ApiError", status: 401 });
  });

  it("passes the abort signal through to fetch so unmount closes the stream", async () => {
    const fetchMock = vi.fn(async () => sseResponse(['data: {"event": "draft_ready"}\n\n']));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await streamLessonEvents(7, () => {}, controller.signal);

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.signal).toBe(controller.signal);
  });
});
