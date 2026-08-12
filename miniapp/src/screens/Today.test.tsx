import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Today from "./Today";
import type { LessonData } from "../lib/types";
import * as telegram from "../lib/telegram";
import * as sse from "../lib/sse";

const BASE: LessonData = {
  group: { id: 1, name: "Beginners A" },
  lesson: {
    id: 7,
    date: "2026-08-10",
    topic: "Present Perfect",
    homework: "Workbook 42-43",
    summary_public: null,
    status: "draft",
    has_audio: false,
  },
  students: [
    { id: 11, full_name: "Aziza Karimova" },
    { id: 12, full_name: "Bobur Toshmatov" },
  ],
  attendance: [],
};

/** Captured MainButton handler -- Telegram holds it, so tests fire it the same
 * way a real tap would instead of clicking a DOM node that does not exist. */
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

/** fetch stub: GET /api/today returns `today`, writes return {ok:true} unless
 * `failWrites` is set. Returns the mock so tests can inspect request bodies. */
function stubFetch(today: LessonData, { failWrites = false } = {}) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/api/today")) {
      return { ok: true, status: 200, json: async () => today } as Response;
    }
    if (failWrites) return { ok: false, status: 500, json: async () => ({}) } as Response;
    void init;
    return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderToday() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <Today />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

interface WriteCall {
  url: string;
  method: string;
  body: string;
}

/** Every non-GET-/api/today call the component made, narrowed to the fields
 * these tests assert on so each one is not re-narrowing RequestInit. */
function writeCalls(fetchMock: ReturnType<typeof vi.fn>): WriteCall[] {
  return (fetchMock.mock.calls as unknown as Array<[string, RequestInit | undefined]>)
    .filter(([url]) => !String(url).endsWith("/api/today"))
    .map(([url, init]) => ({
      url: String(url),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : "",
    }));
}

beforeEach(() => {
  stubTelegram();
});

describe("Today — loading and empty states", () => {
  it("shows a loading message before the request resolves", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderToday();
    expect(screen.getByText("Юкланмоқда...")).toBeInTheDocument();
  });

  it("shows an error message when /api/today fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    renderToday();
    expect(await screen.findByText("Маълумот юкланмади. Қайта очинг.")).toBeInTheDocument();
  });

  it("says there is no lesson today when the backend returns no group", async () => {
    stubFetch({ group: null, lesson: null, students: [], attendance: [] });
    renderToday();
    expect(await screen.findByText("Бугун дарс йўқ.")).toBeInTheDocument();
    expect(telegram.setMainButton).not.toHaveBeenCalled();
  });

  it("prompts registration when the group has no students yet", async () => {
    stubFetch({ ...BASE, students: [] });
    renderToday();
    expect(
      await screen.findByText("Бу гуруҳда ҳали ўқувчи йўқ. Улар ботга /start юборсин."),
    ).toBeInTheDocument();
  });
});

describe("Today — rendering the lesson", () => {
  it("shows the group, the Uzbek-formatted date and one row per student", async () => {
    stubFetch(BASE);
    renderToday();

    expect(await screen.findByText("Beginners A")).toBeInTheDocument();
    expect(screen.getByText("10 август 2026")).toBeInTheDocument();
    expect(screen.getByText("Aziza Karimova")).toBeInTheDocument();
    expect(screen.getByText("Bobur Toshmatov")).toBeInTheDocument();
  });

  it("pre-fills topic and homework from the lesson", async () => {
    stubFetch(BASE);
    renderToday();
    await waitFor(() => expect(screen.getByLabelText("Мавзу")).toHaveValue("Present Perfect"));
    expect(screen.getByLabelText("Уй вазифаси")).toHaveValue("Workbook 42-43");
  });

  it("pre-fills rows from existing attendance (an AI draft or an earlier save)", async () => {
    stubFetch({
      ...BASE,
      attendance: [
        { id: 91, student_id: 11, status: "late", grade: 4, note_public: "Кечикди" },
      ],
    });
    renderToday();

    await screen.findByText("Aziza Karimova");
    const azizaAttendance = screen.getByRole("group", { name: "Aziza Karimova — давомат" });
    const azizaGrades = screen.getByRole("group", { name: "Aziza Karimova — баҳо" });
    expect(within(azizaAttendance).getByRole("button", { name: "🕐 Кеч" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(within(azizaGrades).getByRole("button", { name: "4" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByLabelText("Aziza Karimova — изоҳ")).toHaveValue("Кечикди");
  });
});

describe("Today — saving", () => {
  it("PUTs attendance then POSTs confirm, and reports success", async () => {
    const fetchMock = stubFetch(BASE);
    const user = renderToday();
    await screen.findByText("Beginners A");

    await user.click(screen.getAllByRole("button", { name: "5" })[0]);
    mainButtonHandler!();

    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    expect(writeCalls(fetchMock)).toMatchObject([
      { url: "http://api.test/api/lessons/7/attendance", method: "PUT" },
      { url: "http://api.test/api/lessons/7/confirm", method: "POST" },
    ]);
    expect(telegram.haptic).toHaveBeenCalled();
  });

  it("saves edits made after the MainButton was registered", async () => {
    // Regression guard: registering the handler once per [data, saved] captures
    // the form state from that render, so without a live ref every later edit
    // would be silently dropped on save.
    const fetchMock = stubFetch(BASE);
    const user = renderToday();
    await screen.findByText("Beginners A");

    await user.clear(screen.getByLabelText("Мавзу"));
    await user.type(screen.getByLabelText("Мавзу"), "Past Simple");
    await user.click(screen.getAllByRole("button", { name: "🕐 Кеч" })[0]);
    await user.type(screen.getByLabelText("Aziza Karimova — изоҳ"), "Яхши");
    mainButtonHandler!();

    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const body = JSON.parse(writeCalls(fetchMock)[0].body);
    expect(body.topic).toBe("Past Simple");
    expect(body.items[0]).toMatchObject({
      student_id: 11,
      status: "late",
      note_public: "Яхши",
    });
  });

  it("sends every student, defaulting untouched ones to present with no grade", async () => {
    const fetchMock = stubFetch(BASE);
    renderToday();
    await screen.findByText("Beginners A");

    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const body = JSON.parse(writeCalls(fetchMock)[0].body);
    expect(body.items).toEqual([
      { student_id: 11, status: "present", grade: null, note_public: null },
      { student_id: 12, status: "present", grade: null, note_public: null },
    ]);
  });

  it("never sends a grade for an absent student", async () => {
    const fetchMock = stubFetch(BASE);
    const user = renderToday();
    await screen.findByText("Beginners A");

    await user.click(screen.getAllByRole("button", { name: "5" })[0]);
    await user.click(screen.getAllByRole("button", { name: "❌ Келмади" })[0]);
    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const body = JSON.parse(writeCalls(fetchMock)[0].body);
    expect(body.items[0]).toMatchObject({ status: "absent", grade: null });
  });

  it("sends null instead of a whitespace-only note", async () => {
    const fetchMock = stubFetch(BASE);
    const user = renderToday();
    await screen.findByText("Beginners A");

    await user.type(screen.getByLabelText("Aziza Karimova — изоҳ"), "   ");
    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const body = JSON.parse(writeCalls(fetchMock)[0].body);
    expect(body.items[0].note_public).toBeNull();
  });

  it("hides the MainButton and locks the form after saving", async () => {
    stubFetch(BASE);
    renderToday();
    await screen.findByText("Beginners A");

    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    expect(telegram.hideMainButton).toHaveBeenCalled();
    expect(screen.getByLabelText("Мавзу")).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "✅ Келди" })[0]).toBeDisabled();
  });

  it("shows an error and keeps the form editable when the save fails", async () => {
    stubFetch(BASE, { failWrites: true });
    renderToday();
    await screen.findByText("Beginners A");

    mainButtonHandler!();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сақлаб бўлмади. Қайтадан уриниб кўринг.",
    );
    expect(screen.queryByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Мавзу")).toBeEnabled();
    expect(telegram.hideMainButtonLoading).toHaveBeenCalled();
  });

  it("retries cleanly after a failed save", async () => {
    let fail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/api/today")) {
          return { ok: true, status: 200, json: async () => BASE } as Response;
        }
        if (fail) return { ok: false, status: 500, json: async () => ({}) } as Response;
        return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
      }),
    );
    renderToday();
    await screen.findByText("Beginners A");

    mainButtonHandler!();
    await screen.findByRole("alert");

    fail = false;
    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a second tap while the first save is still in flight", async () => {
    let releasePut: (() => void) | null = null;
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).endsWith("/api/today")) {
        return { ok: true, status: 200, json: async () => BASE } as Response;
      }
      if (String(url).endsWith("/attendance")) {
        await new Promise<void>((resolve) => {
          releasePut = resolve;
        });
      }
      return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderToday();
    await screen.findByText("Beginners A");

    mainButtonHandler!();
    await waitFor(() => expect(releasePut).not.toBeNull());
    mainButtonHandler!(); // double tap while the PUT is pending

    releasePut!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const writes = fetchMock.mock.calls.filter(([url]) => !String(url).endsWith("/api/today"));
    expect(writes.filter(([url]) => String(url).endsWith("/attendance"))).toHaveLength(1);
    expect(writes.filter(([url]) => String(url).endsWith("/confirm"))).toHaveLength(1);
  });
});

describe("Today — an already-saved lesson", () => {
  const SAVED: LessonData = {
    ...BASE,
    lesson: { ...BASE.lesson!, status: "saved" },
    attendance: [{ id: 91, student_id: 11, status: "present", grade: 5, note_public: null }],
  };

  it("renders read-only with no MainButton", async () => {
    stubFetch(SAVED);
    renderToday();

    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");
    expect(telegram.setMainButton).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Мавзу")).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "❌ Келмади" })[0]).toBeDisabled();
  });
});

describe("Today — AI draft over SSE", () => {
  /** A lesson the bot has received a voice note for, with no draft written yet. */
  const AWAITING_AI: LessonData = {
    ...BASE,
    lesson: { ...BASE.lesson!, topic: null, homework: null, has_audio: true },
    attendance: [],
  };

  /** The same lesson once the pipeline has written its draft. */
  const WITH_DRAFT: LessonData = {
    ...AWAITING_AI,
    lesson: { ...AWAITING_AI.lesson!, topic: "Present Perfect", homework: "Workbook 42-43" },
    attendance: [{ id: 91, student_id: 11, status: "late", grade: 4, note_public: "Кечикди" }],
  };

  function controllableStream() {
    let emit: (e: sse.LessonEvent) => void = () => {};
    let close: () => void = () => {};
    const spy = vi.spyOn(sse, "streamLessonEvents").mockImplementation((_id, onEvent) => {
      emit = onEvent;
      return new Promise<void>((resolve) => {
        close = resolve;
      });
    });
    return { spy, emit: (e: sse.LessonEvent) => emit(e), close: () => close() };
  }

  /** GET /api/today returns each entry of `pages` in turn, so a refetch can
   * observe the draft the first load did not have. */
  function stubPagedFetch(pages: LessonData[]) {
    let call = 0;
    const fn = vi.fn(async (url: string) => {
      if (String(url).endsWith("/api/today")) {
        const page = pages[Math.min(call, pages.length - 1)];
        call += 1;
        return { ok: true, status: 200, json: async () => page } as Response;
      }
      return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  it("shows the spinner while an AI draft is on its way", async () => {
    controllableStream();
    stubPagedFetch([AWAITING_AI]);
    renderToday();

    expect(await screen.findByRole("status")).toHaveTextContent("AI қоралама тайёрланмоқда...");
  });

  it("does not open a stream for a lesson with no voice note", async () => {
    const stream = controllableStream();
    stubPagedFetch([{ ...BASE, attendance: [] }]);
    renderToday();

    await screen.findByText("Beginners A");
    expect(stream.spy).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not open a stream when the draft already landed before the app opened", async () => {
    const stream = controllableStream();
    stubPagedFetch([WITH_DRAFT]);
    renderToday();

    await screen.findByText("Beginners A");
    expect(stream.spy).not.toHaveBeenCalled();
  });

  it("does not open a stream for a lesson that is already saved", async () => {
    const stream = controllableStream();
    stubPagedFetch([
      { ...AWAITING_AI, lesson: { ...AWAITING_AI.lesson!, status: "saved" } },
    ]);
    renderToday();

    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");
    expect(stream.spy).not.toHaveBeenCalled();
  });

  it("refetches and fills the form when the draft is ready", async () => {
    const stream = controllableStream();
    stubPagedFetch([AWAITING_AI, WITH_DRAFT]);
    renderToday();

    await screen.findByRole("status");
    expect(screen.getByLabelText("Мавзу")).toHaveValue("");

    stream.emit({ event: "draft_ready" });

    await waitFor(() => expect(screen.getByLabelText("Мавзу")).toHaveValue("Present Perfect"));
    expect(screen.getByLabelText("Уй вазифаси")).toHaveValue("Workbook 42-43");
    const azizaAtt = screen.getByRole("group", { name: "Aziza Karimova — давомат" });
    expect(within(azizaAtt).getByRole("button", { name: "🕐 Кеч" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByLabelText("Aziza Karimova — изоҳ")).toHaveValue("Кечикди");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps the teacher's edits and drops the draft when the form is not pristine", async () => {
    const stream = controllableStream();
    stubPagedFetch([AWAITING_AI, WITH_DRAFT]);
    const user = renderToday();

    await screen.findByRole("status");
    await user.type(screen.getByLabelText("Мавзу"), "Қўлда");
    await user.click(screen.getAllByRole("button", { name: "❌ Келмади" })[0]);

    stream.emit({ event: "draft_ready" });

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Мавзу")).toHaveValue("Қўлда");
    const azizaAtt = screen.getByRole("group", { name: "Aziza Karimova — давомат" });
    expect(within(azizaAtt).getByRole("button", { name: "❌ Келмади" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("saves the auto-filled draft as-is when the teacher just taps save", async () => {
    const stream = controllableStream();
    const fetchMock = stubPagedFetch([AWAITING_AI, WITH_DRAFT]);
    renderToday();

    await screen.findByRole("status");
    stream.emit({ event: "draft_ready" });
    await waitFor(() => expect(screen.getByLabelText("Мавзу")).toHaveValue("Present Perfect"));

    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    const body = JSON.parse(writeCalls(fetchMock)[0].body);
    expect(body.topic).toBe("Present Perfect");
    expect(body.items[0]).toMatchObject({ student_id: 11, status: "late", grade: 4 });
  });

  it("warns and leaves the form editable when no draft arrives", async () => {
    const stream = controllableStream();
    stubPagedFetch([AWAITING_AI]);
    renderToday();

    await screen.findByRole("status");
    stream.emit({ event: "timeout" });

    expect(await screen.findByRole("status")).toHaveTextContent(
      "⚠️ AI қоралама келмади — қўлда киритинг",
    );
    expect(screen.getByLabelText("Мавзу")).toBeEnabled();
    expect(mainButtonHandler).not.toBeNull();
  });

  it("hides the warning once the lesson is saved by hand", async () => {
    const stream = controllableStream();
    stubPagedFetch([AWAITING_AI]);
    renderToday();

    await screen.findByRole("status");
    stream.emit({ event: "timeout" });
    await screen.findByText("⚠️ AI қоралама келмади — қўлда киритинг");

    mainButtonHandler!();
    await screen.findByText("✅ Сақланди. Ўқувчиларга хабар юборилмоқда.");

    expect(screen.queryByText("⚠️ AI қоралама келмади — қўлда киритинг")).not.toBeInTheDocument();
  });
});
