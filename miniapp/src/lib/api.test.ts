import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, authenticate, clearToken, getToken } from "./api";

const BASE = import.meta.env.VITE_API_URL as string;

function mockFetch(...responses: Array<{ ok: boolean; status: number; body?: unknown }>) {
  const fn = vi.fn();
  for (const r of responses) {
    fn.mockResolvedValueOnce({
      ok: r.ok,
      status: r.status,
      json: async () => r.body,
    });
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  clearToken();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("authenticate", () => {
  it("posts initData and keeps the token in memory only", async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, body: { access_token: "jwt-123" } });

    await authenticate("auth_date=1&user=%7B%7D&hash=abc");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/api/auth/telegram`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ init_data: "auth_date=1&user=%7B%7D&hash=abc" });
    expect(getToken()).toBe("jwt-123");
    // in-memory only: nothing persisted where a later page load could read it
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("throws ApiError(403) for a non-teacher so App can show the right message", async () => {
    mockFetch({ ok: false, status: 403 });

    await expect(authenticate("x")).rejects.toMatchObject({ name: "ApiError", status: 403 });
    expect(getToken()).toBeNull();
  });

  it("throws ApiError(401) for stale or tampered initData", async () => {
    mockFetch({ ok: false, status: 401 });

    await expect(authenticate("x")).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
  });
});

describe("apiFetch", () => {
  it("attaches the bearer token from a prior authenticate()", async () => {
    const fetchMock = mockFetch(
      { ok: true, status: 200, body: { access_token: "jwt-123" } },
      { ok: true, status: 200, body: { group: null } },
    );

    await authenticate("x");
    const data = await apiFetch<{ group: null }>("/api/today");

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe(`${BASE}/api/today`);
    expect(init.headers.Authorization).toBe("Bearer jwt-123");
    expect(data).toEqual({ group: null });
  });

  it("sends no Authorization header when unauthenticated", async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, body: {} });

    await apiFetch("/api/today");

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("passes method and body through, keeping the JSON content type", async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, body: { ok: true } });

    await apiFetch("/api/lessons/1/attendance", {
      method: "PUT",
      body: JSON.stringify({ items: [] }),
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(init.body).toBe('{"items":[]}');
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("throws ApiError carrying the status on a failed response", async () => {
    mockFetch({ ok: false, status: 404 });

    await expect(apiFetch("/api/lessons?date=2026-08-10")).rejects.toMatchObject({
      status: 404,
    });
  });
});
