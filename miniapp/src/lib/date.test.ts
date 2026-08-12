import { describe, expect, it } from "vitest";
import { formatDateUz, previousDay, todayIso, yesterdayIso } from "./date";

describe("formatDateUz", () => {
  it("matches the backend format_date_uz output", () => {
    expect(formatDateUz("2026-08-11")).toBe("11 август 2026");
    expect(formatDateUz("2026-01-01")).toBe("1 январ 2026");
    expect(formatDateUz("2026-12-31")).toBe("31 декабр 2026");
  });

  it("does not shift the day across timezones", () => {
    // new Date("2026-08-01") parses as UTC midnight, which is the previous day
    // west of Greenwich; the manual parse must not have that behaviour.
    expect(formatDateUz("2026-08-01")).toBe("1 август 2026");
  });

  it("returns the input unchanged when it is not an ISO date", () => {
    expect(formatDateUz("")).toBe("");
    expect(formatDateUz("11.08.2026")).toBe("11.08.2026");
    expect(formatDateUz("2026-13-01")).toBe("2026-13-01");
  });
});

describe("todayIso", () => {
  it("reports the Bishkek day, not the UTC one", () => {
    // 21:00 UTC on 10 Aug is already 03:00 on 11 Aug in Bishkek (UTC+6).
    // toISOString() would answer "2026-08-10" and fetch the wrong lesson.
    expect(todayIso(new Date("2026-08-10T21:00:00Z"))).toBe("2026-08-11");
  });

  it("still reports the earlier day just before Bishkek midnight", () => {
    expect(todayIso(new Date("2026-08-10T17:59:00Z"))).toBe("2026-08-10");
  });

  it("zero-pads single-digit months and days", () => {
    expect(todayIso(new Date("2026-01-05T06:00:00Z"))).toBe("2026-01-05");
  });
});

describe("previousDay", () => {
  it("steps back one day", () => {
    expect(previousDay("2026-08-11")).toBe("2026-08-10");
  });

  it("crosses a month boundary", () => {
    expect(previousDay("2026-08-01")).toBe("2026-07-31");
  });

  it("crosses a year boundary", () => {
    expect(previousDay("2026-01-01")).toBe("2025-12-31");
  });

  it("handles a leap day", () => {
    expect(previousDay("2028-03-01")).toBe("2028-02-29");
    expect(previousDay("2027-03-01")).toBe("2027-02-28");
  });

  it("returns the input unchanged when it is not an ISO date", () => {
    expect(previousDay("kecha")).toBe("kecha");
  });
});

describe("yesterdayIso", () => {
  it("is the day before the Bishkek today", () => {
    expect(yesterdayIso(new Date("2026-08-10T21:00:00Z"))).toBe("2026-08-10");
    expect(yesterdayIso(new Date("2026-08-10T17:59:00Z"))).toBe("2026-08-09");
  });
});
