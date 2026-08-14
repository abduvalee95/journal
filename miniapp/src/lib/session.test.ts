/** Session and draft survival — the two paths that used to lose the teacher's
 * work outright. See docs/audit-2026-08-14.md (C4, C5, H13). */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  REQUEST_TIMEOUT_MS,
  SessionExpiredError,
  apiFetch,
  authenticate,
  clearToken,
} from "./api";
import { clearDraft, loadDraft, saveDraft } from "./draft";

const OK = { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;

function json(status: number, body: unknown): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

afterEach(() => {
  clearToken();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

async function signIn(): Promise<void> {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json(200, { access_token: "jwt-1", expires_in: 1800 })),
  );
  await authenticate("auth_date=1&hash=abc");
}

describe("session renewal", () => {
  it("refreshes once and retries the request when the token has expired", async () => {
    await signIn();

    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        calls.push(String(url));
        if (String(url).endsWith("/api/auth/refresh")) {
          return json(200, { access_token: "jwt-2", expires_in: 1800 });
        }
        // First data call 401s (token aged out), the retry after the refresh
        // succeeds.
        return calls.filter((c) => c.endsWith("/api/today")).length === 1 ? json(401, {}) : OK;
      }),
    );

    await expect(apiFetch("/api/today")).resolves.toEqual({ ok: true });
    expect(calls.filter((c) => c.endsWith("/api/auth/refresh"))).toHaveLength(1);
    expect(calls.filter((c) => c.endsWith("/api/today"))).toHaveLength(2);
  });

  it("reports an unrecoverable session rather than a generic save failure", async () => {
    await signIn();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).endsWith("/api/auth/refresh") ? json(401, {}) : json(401, {}),
      ),
    );

    // Telegram will not hand out fresh initData while the app is open, so this
    // genuinely cannot be recovered from inside the Mini App -- the message the
    // teacher sees has to say so.
    await expect(apiFetch("/api/today")).rejects.toBeInstanceOf(SessionExpiredError);
  });

  it("does not attempt a refresh when there was never a session", async () => {
    const fetchMock = vi.fn(async () => json(401, {}));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/today")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("request timeout", () => {
  it("aborts a request that never settles", async () => {
    vi.useFakeTimers();

    let aborted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => {
              aborted = true;
              reject(new DOMException("Aborted", "AbortError"));
            });
          }),
      ),
    );

    const pending = apiFetch("/api/today").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 100);
    await pending;

    // Without this the MainButton spun forever: the promise never settled, so
    // the `finally` that clears the in-flight guard never ran and every further
    // tap was swallowed.
    expect(aborted).toBe(true);
  });
});

describe("unsaved draft", () => {
  it("round-trips the form state for a lesson", () => {
    saveDraft(7, {
      edits: [
        [
          11,
          { id: 11, full_name: "Aziza", status: "late", grade: 4, note_public: "ok", att_id: null },
        ],
      ],
      topicEdit: "Қўлда",
      homeworkEdit: null,
      summaryEdit: null,
    });

    const restored = loadDraft(7);
    expect(restored?.topicEdit).toBe("Қўлда");
    expect(restored?.edits[0][1].status).toBe("late");
  });

  it("keeps drafts for different lessons apart", () => {
    saveDraft(1, { edits: [], topicEdit: "one", homeworkEdit: null, summaryEdit: null });
    saveDraft(2, { edits: [], topicEdit: "two", homeworkEdit: null, summaryEdit: null });
    expect(loadDraft(1)?.topicEdit).toBe("one");
    expect(loadDraft(2)?.topicEdit).toBe("two");
  });

  it("returns null rather than throwing on stored garbage", () => {
    sessionStorage.setItem("ustoz-draft:9", "{ not json");
    expect(loadDraft(9)).toBeNull();
  });

  it("survives storage being unavailable", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    // Must never stop the teacher entering a lesson.
    expect(() =>
      saveDraft(3, { edits: [], topicEdit: "x", homeworkEdit: null, summaryEdit: null }),
    ).not.toThrow();
    setItem.mockRestore();
  });

  it("clears a lesson's draft", () => {
    saveDraft(5, { edits: [], topicEdit: "x", homeworkEdit: null, summaryEdit: null });
    clearDraft(5);
    expect(loadDraft(5)).toBeNull();
  });

  it("ignores a null lesson id", () => {
    expect(loadDraft(null)).toBeNull();
    expect(() =>
      saveDraft(null, { edits: [], topicEdit: null, homeworkEdit: null, summaryEdit: null }),
    ).not.toThrow();
  });
});
