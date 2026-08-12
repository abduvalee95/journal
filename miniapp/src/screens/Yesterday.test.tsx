import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Yesterday from "./Yesterday";
import type { LessonData } from "../lib/types";
import * as telegram from "../lib/telegram";
import * as dateLib from "../lib/date";

const YESTERDAY: LessonData = {
  group: { id: 1, name: "Beginners A" },
  lesson: {
    id: 6,
    date: "2026-08-09",
    topic: "Past Simple",
    homework: "Workbook 40-41",
    summary_public: null,
    status: "saved",
    has_audio: true,
  },
  students: [
    { id: 11, full_name: "Aziza Karimova" },
    { id: 12, full_name: "Bobur Toshmatov" },
  ],
  attendance: [
    { id: 91, student_id: 11, status: "present", grade: 4, note_public: "Яхши" },
    { id: 92, student_id: 12, status: "absent", grade: null, note_public: null },
  ],
};

let mainButtonHandler: (() => void) | null = null;

function stubTelegram() {
  mainButtonHandler = null;
  vi.spyOn(telegram, "setMainButton").mockImplementation((_text, onClick) => {
    mainButtonHandler = onClick;
  });
  vi.spyOn(telegram, "hideMainButton").mockImplementation(() => {
    mainButtonHandler = null;
  });
  vi.spyOn(telegram, "showMainButtonLoading").mockImplementation(() => {});
  vi.spyOn(telegram, "hideMainButtonLoading").mockImplementation(() => {});
  vi.spyOn(telegram, "haptic").mockImplementation(() => {});
}

function stubFetch(lesson: LessonData, { failWrites = false } = {}) {
  const fn = vi.fn(async (url: string) => {
    if (String(url).includes("/api/lessons?date=")) {
      return { ok: true, status: 200, json: async () => lesson } as Response;
    }
    if (failWrites) return { ok: false, status: 500, json: async () => ({}) } as Response;
    return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderYesterday() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Yesterday />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

interface WriteCall {
  url: string;
  method: string;
  body: string;
}

function writeCalls(fetchMock: ReturnType<typeof vi.fn>): WriteCall[] {
  return (fetchMock.mock.calls as unknown as Array<[string, RequestInit | undefined]>)
    .filter(([url]) => !String(url).includes("/api/lessons?date="))
    .map(([url, init]) => ({
      url: String(url),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : "",
    }));
}

beforeEach(() => {
  stubTelegram();
  // Pinned so the screen always asks for the fixture's date. The Bishkek-day
  // arithmetic itself is covered in date.test.ts.
  vi.spyOn(dateLib, "yesterdayIso").mockReturnValue("2026-08-09");
});

describe("Yesterday — loading and empty states", () => {
  it("shows a loading message first", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderYesterday();
    expect(screen.getByText("Юкланмоқда...")).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    renderYesterday();
    expect(await screen.findByText("Маълумот юкланмади. Қайта очинг.")).toBeInTheDocument();
  });

  it("says there was no lesson when the backend returns nothing", async () => {
    stubFetch({ group: null, lesson: null, students: [], attendance: [] });
    renderYesterday();
    expect(await screen.findByText("Кеча дарс бўлмаган.")).toBeInTheDocument();
    expect(telegram.setMainButton).not.toHaveBeenCalled();
  });
});

describe("Yesterday — rendering", () => {
  it("requests the previous calendar day from the lessons endpoint", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    renderYesterday();
    await screen.findByText("Кеча — Beginners A");
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/lessons?date=2026-08-09");
  });

  it("shows the group, the date and the no-notification warning", async () => {
    stubFetch(YESTERDAY);
    renderYesterday();

    expect(await screen.findByText("Кеча — Beginners A")).toBeInTheDocument();
    expect(screen.getByText("9 август 2026")).toBeInTheDocument();
    expect(screen.getByText("⚠️ Тузатиш ўқувчиларга хабар юбормайди")).toBeInTheDocument();
  });

  it("pre-fills each row from the saved attendance", async () => {
    stubFetch(YESTERDAY);
    renderYesterday();

    await screen.findByText("Aziza Karimova");
    const aziza = screen.getByRole("group", { name: "Aziza Karimova — давомат" });
    expect(within(aziza).getByRole("button", { name: "✅ Келди" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      within(screen.getByRole("group", { name: "Aziza Karimova — баҳо" })).getByRole("button", {
        name: "4",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Aziza Karimova — изоҳ")).toHaveValue("Яхши");
  });

  it("offers no save button until something is changed", async () => {
    stubFetch(YESTERDAY);
    renderYesterday();
    await screen.findByText("Кеча — Beginners A");
    expect(telegram.setMainButton).not.toHaveBeenCalled();
  });
});

describe("Yesterday — correcting", () => {
  it("shows the save button once a row is edited", async () => {
    stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);

    await waitFor(() => expect(telegram.setMainButton).toHaveBeenCalled());
    expect(vi.mocked(telegram.setMainButton).mock.calls[0][0]).toBe("Сақлаш (жим)");
  });

  it("PATCHes only the rows that changed, and never calls confirm", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    const writes = writeCalls(fetchMock);
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({
      url: "http://api.test/api/attendance/91",
      method: "PATCH",
    });
    expect(JSON.parse(writes[0].body)).toEqual({
      student_id: 11,
      status: "late",
      grade: 4,
      note_public: "Яхши",
    });
    expect(writes.some((w) => w.url.includes("/confirm"))).toBe(false);
  });

  it("sends every corrected row when several change", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    await user.click(screen.getAllByRole("button", { name: "✅ Келди" })[1]);
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    const urls = writeCalls(fetchMock).map((w) => w.url);
    expect(urls).toHaveLength(2);
    expect(urls).toContain("http://api.test/api/attendance/91");
    expect(urls).toContain("http://api.test/api/attendance/92");
  });

  it("never sends a grade for a student corrected to absent", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "❌ Келмади" })[0]);
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    expect(JSON.parse(writeCalls(fetchMock)[0].body)).toMatchObject({
      status: "absent",
      grade: null,
    });
  });

  it("sends null instead of a whitespace-only note", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.clear(screen.getByLabelText("Aziza Karimova — изоҳ"));
    await user.type(screen.getByLabelText("Aziza Karimova — изоҳ"), "   ");
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    expect(JSON.parse(writeCalls(fetchMock)[0].body).note_public).toBeNull();
  });

  it("saves an edit made after the save button first appeared", async () => {
    // Same stale-closure guard as the Today screen: Telegram keeps whichever
    // function it was handed, so it must read live state.
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    await waitFor(() => expect(mainButtonHandler).not.toBeNull());
    await user.type(screen.getByLabelText("Aziza Karimova — изоҳ"), " жуда");
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    expect(JSON.parse(writeCalls(fetchMock)[0].body).note_public).toBe("Яхши жуда");
  });

  it("hides the save button and clears the notice after a further edit", async () => {
    stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");
    // the baseline moved, so the freshly saved state counts as unchanged
    expect(telegram.hideMainButton).toHaveBeenCalled();

    await user.click(screen.getAllByRole("button", { name: "❌ Келмади" })[0]);
    await waitFor(() =>
      expect(screen.queryByText("✅ Тузатишлар сақланди.")).not.toBeInTheDocument(),
    );
  });

  it("does not re-send a row that was corrected back to its original value", async () => {
    const fetchMock = stubFetch(YESTERDAY);
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    await user.click(screen.getAllByRole("button", { name: "✅ Келди" })[0]);

    await waitFor(() => expect(telegram.hideMainButton).toHaveBeenCalled());
    expect(mainButtonHandler).toBeNull();
    expect(writeCalls(fetchMock)).toHaveLength(0);
  });

  it("shows an error and keeps the form editable when a PATCH fails", async () => {
    stubFetch(YESTERDAY, { failWrites: true });
    const user = renderYesterday();
    await screen.findByText("Кеча — Beginners A");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    mainButtonHandler!();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Тузатишлар сақланмади. Қайтадан уриниб кўринг.",
    );
    expect(screen.queryByText("✅ Тузатишлар сақланди.")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]).toBeEnabled();
    expect(telegram.hideMainButtonLoading).toHaveBeenCalled();
  });
});

describe("Yesterday — a student with no attendance record", () => {
  const WITH_LATE_JOINER: LessonData = {
    ...YESTERDAY,
    students: [...YESTERDAY.students, { id: 13, full_name: "Dildora Yusupova" }],
  };

  it("renders their row read-only and explains why", async () => {
    stubFetch(WITH_LATE_JOINER);
    renderYesterday();

    await screen.findByText("Dildora Yusupova");
    const dildora = screen.getByRole("group", { name: "Dildora Yusupova — давомат" });
    expect(within(dildora).getByRole("button", { name: "✅ Келди" })).toBeDisabled();
    expect(
      screen.getByText("Dildora Yusupova — бу дарсда ёзув йўқ, тузатиб бўлмайди."),
    ).toBeInTheDocument();
  });

  it("leaves the other students correctable", async () => {
    const fetchMock = stubFetch(WITH_LATE_JOINER);
    const user = renderYesterday();
    await screen.findByText("Dildora Yusupova");

    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    mainButtonHandler!();
    await screen.findByText("✅ Тузатишлар сақланди.");

    expect(writeCalls(fetchMock).map((w) => w.url)).toEqual([
      "http://api.test/api/attendance/91",
    ]);
  });
});
