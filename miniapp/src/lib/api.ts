const BASE = import.meta.env.VITE_API_URL as string;

/** JWT lives in memory only -- never localStorage/sessionStorage, per the
 * design doc: the token is teacher-scoped and an in-memory token cannot be
 * lifted out of storage by anything that later renders in this webview. */
let _token: string | null = null;
let _expiresAt = 0;
let _refreshTimer: ReturnType<typeof setTimeout> | null = null;
let _inFlightRefresh: Promise<boolean> | null = null;

/** How long a request may hang before we give up on it. Without this a stalled
 * VPS left the MainButton spinning forever with no way for the teacher to
 * clear it, because the promise never settled and the `finally` never ran. */
export const REQUEST_TIMEOUT_MS = 15_000;

/** Renew this long before the token actually expires, so a save at the end of
 * a 90-minute lesson never lands on a dead token. */
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** The session is gone and cannot be recovered from inside the Mini App.
 *
 * Telegram does not refresh `initData` while the app stays open, and the
 * backend rejects an `auth_date` older than five minutes, so re-running the
 * initData exchange is not a way back. The teacher has to reopen the app --
 * which is why the draft is persisted before we ever get here. */
export class SessionExpiredError extends ApiError {
  constructor() {
    super(401, "Session expired");
    this.name = "SessionExpiredError";
  }
}

/** An abort signal that fires on our timeout, or on the caller's own signal. */
function withTimeout(signal: AbortSignal | null | undefined, ms: number) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), ms);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener("abort", () => controller.abort(signal.reason), { once: true });
  }
  return { signal: controller.signal, done: () => clearTimeout(timer) };
}

function storeToken(token: string, expiresInSeconds: number | undefined): void {
  _token = token;
  _expiresAt = Date.now() + (expiresInSeconds ?? 1800) * 1000;
  scheduleRefresh();
}

function scheduleRefresh(): void {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  const delay = Math.max(_expiresAt - Date.now() - REFRESH_MARGIN_MS, 1000);
  _refreshTimer = setTimeout(() => {
    void refreshToken();
  }, delay);
}

export function stopTokenRefresh(): void {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  _refreshTimer = null;
}

export async function authenticate(initData: string): Promise<void> {
  const { signal, done } = withTimeout(null, REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}/api/auth/telegram`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: initData }),
      signal,
    });
    if (!res.ok) {
      // 403 = valid Telegram user, wrong person (not the teacher); 401 = bad or
      // stale initData. App.tsx shows a different message for each.
      throw new ApiError(res.status, `Auth failed: ${res.status}`);
    }
    const data = (await res.json()) as { access_token: string; expires_in?: number };
    storeToken(data.access_token, data.expires_in);
  } finally {
    done();
  }
}

/** Exchange the current token for a fresh one. Returns false if that failed. */
export async function refreshToken(): Promise<boolean> {
  if (!_token) return false;
  if (_inFlightRefresh) return _inFlightRefresh;

  _inFlightRefresh = (async () => {
    const { signal, done } = withTimeout(null, REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(`${BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { Authorization: `Bearer ${_token}` },
        signal,
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access_token: string; expires_in?: number };
      storeToken(data.access_token, data.expires_in);
      return true;
    } catch {
      return false;
    } finally {
      done();
      _inFlightRefresh = null;
    }
  })();

  return _inFlightRefresh;
}

async function rawFetch(path: string, options: RequestInit): Promise<Response> {
  const { signal, done } = withTimeout(options.signal, REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${BASE}${path}`, {
      ...options,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(_token ? { Authorization: `Bearer ${_token}` } : {}),
        ...options.headers,
      },
    });
  } finally {
    done();
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (_token && Date.now() > _expiresAt - REFRESH_MARGIN_MS) {
    await refreshToken();
  }

  let res = await rawFetch(path, options);

  if (res.status === 401 && _token) {
    // One retry behind one refresh: clock skew, or a renewal we missed while
    // the app was backgrounded and timers were throttled.
    if (await refreshToken()) {
      res = await rawFetch(path, options);
    } else {
      throw new SessionExpiredError();
    }
  }

  if (!res.ok) throw new ApiError(res.status, `API ${res.status}: ${path}`);
  return (await res.json()) as T;
}

/** Used by the SSE reader in sse.ts, which needs to build the request itself.
 * `EventSource` cannot send an Authorization header and the stream endpoint is
 * Bearer-protected, so it is read with `fetch` + a ReadableStream reader --
 * putting the JWT in the query string instead would leak it into server access
 * logs, browser history and Referer headers. */
export function getToken(): string | null {
  return _token;
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

/** Test seam: drop the in-memory token. */
export function clearToken(): void {
  _token = null;
  _expiresAt = 0;
  stopTokenRefresh();
}
