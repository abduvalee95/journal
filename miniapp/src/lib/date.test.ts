import { describe, expect, it } from "vitest";
import { formatDateUz } from "./date";

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
