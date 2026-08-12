import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import type { LessonData } from "./lib/types";
import * as telegram from "./lib/telegram";

const EMPTY: LessonData = { group: null, lesson: null, students: [], attendance: [] };

function stubTelegram() {
  vi.spyOn(telegram, "expandApp").mockImplementation(() => {});
  vi.spyOn(telegram, "setMainButton").mockImplementation(() => {});
  vi.spyOn(telegram, "hideMainButton").mockImplementation(() => {});
  vi.spyOn(telegram, "showMainButtonLoading").mockImplementation(() => {});
  vi.spyOn(telegram, "hideMainButtonLoading").mockImplementation(() => {});
  vi.spyOn(telegram, "haptic").mockImplementation(() => {});
}

/** Auth succeeds unless `authStatus` says otherwise; both screens then report
 * that there is no lesson, which is enough to tell them apart on screen. */
function stubFetch({ authStatus = 200 } = {}) {
  const fn = vi.fn(async (url: string) => {
    if (String(url).endsWith("/api/auth/telegram")) {
      return {
        ok: authStatus < 400,
        status: authStatus,
        json: async () => ({ access_token: "jwt-123" }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => EMPTY } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

beforeEach(() => {
  stubTelegram();
});

describe("App — authentication", () => {
  it("shows a teacher-only message when the backend rejects the user", async () => {
    stubFetch({ authStatus: 403 });
    renderApp();
    expect(await screen.findByText("Кириш рухсат этилмади. Фақат устоз учун.")).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("shows a connection message for any other auth failure", async () => {
    stubFetch({ authStatus: 401 });
    renderApp();
    expect(await screen.findByText("Уланиб бўлмади. Телеграм орқали қайта очинг.")).toBeInTheDocument();
  });

  it("authenticates once despite StrictMode double-invoking effects", async () => {
    const fetchMock = stubFetch();
    renderApp();
    await screen.findByRole("tablist");
    const authCalls = fetchMock.mock.calls.filter(([url]) =>
      String(url).endsWith("/api/auth/telegram"),
    );
    expect(authCalls).toHaveLength(1);
  });
});

describe("App — navigation", () => {
  it("opens on the Today tab", async () => {
    stubFetch();
    renderApp();

    expect(await screen.findByText("Бугун дарс йўқ.")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Бугун" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Кеча" })).toHaveAttribute("aria-selected", "false");
  });

  it("switches to the Yesterday screen and back", async () => {
    stubFetch();
    const user = renderApp();
    await screen.findByRole("tablist");

    await user.click(screen.getByRole("tab", { name: "Кеча" }));
    await waitFor(() => expect(screen.getByText("Кеча дарс бўлмаган.")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "Кеча" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("tab", { name: "Бугун" }));
    await waitFor(() => expect(screen.getByText("Бугун дарс йўқ.")).toBeInTheDocument());
    expect(screen.queryByText("Кеча дарс бўлмаган.")).not.toBeInTheDocument();
  });

  it("asks each screen's own endpoint", async () => {
    const fetchMock = stubFetch();
    const user = renderApp();
    await screen.findByText("Бугун дарс йўқ.");
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/today"))).toBe(true);

    await user.click(screen.getByRole("tab", { name: "Кеча" }));
    await screen.findByText("Кеча дарс бўлмаган.");
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/api/lessons?date=")),
    ).toBe(true);
  });

  it("releases the Telegram MainButton when a screen is swapped out", async () => {
    stubFetch();
    const user = renderApp();
    await screen.findByText("Бугун дарс йўқ.");
    vi.mocked(telegram.hideMainButton).mockClear();

    await user.click(screen.getByRole("tab", { name: "Кеча" }));
    await screen.findByText("Кеча дарс бўлмаган.");

    expect(telegram.hideMainButton).toHaveBeenCalled();
  });
});
