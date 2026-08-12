const BASE = import.meta.env.VITE_API_URL as string;

/** JWT lives in memory only -- never localStorage/sessionStorage, per the
 * design doc: the token is teacher-scoped and a 30 min in-memory token cannot
 * be lifted out of storage by anything that later renders in this webview. */
let _token: string | null = null;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function authenticate(initData: string): Promise<void> {
  const res = await fetch(`${BASE}/api/auth/telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) {
    // 403 = valid Telegram user, wrong person (not the teacher); 401 = bad or
    // stale initData. App.tsx shows a different message for each.
    throw new ApiError(res.status, `Auth failed: ${res.status}`);
  }
  const data = (await res.json()) as { access_token: string };
  _token = data.access_token;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(_token ? { Authorization: `Bearer ${_token}` } : {}),
      ...options.headers,
    },
  });
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
}
