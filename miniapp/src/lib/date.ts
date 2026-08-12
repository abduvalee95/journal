/** The teacher's timezone, matching backend `app/utils/localtime.py`. Lesson
 * dates are Bishkek calendar days, so the client must ask which day it is
 * there rather than trusting the device clock's zone. */
const TZ = "Asia/Bishkek";

const MONTHS_UZ = [
  "январ",
  "феврал",
  "март",
  "апрел",
  "май",
  "июн",
  "июл",
  "август",
  "сентябр",
  "октябр",
  "ноябр",
  "декабр",
];

/** Mirror of backend `format_date_uz` (app/utils/localtime.py): "2026-08-11"
 * -> "11 август 2026". Parsed by hand rather than with `new Date(iso)`, which
 * would read the string as UTC midnight and shift the day in Asia/Bishkek. */
export function formatDateUz(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const monthName = MONTHS_UZ[Number(month) - 1];
  if (!monthName) return iso;
  return `${Number(day)} ${monthName} ${Number(year)}`;
}

const ISO_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** Today's date as the backend sees it -- the Bishkek calendar day, not the
 * device's. The task brief reached for `new Date().toISOString()`, which
 * reports the UTC day: for a teacher opening the app before 06:00 local that
 * is still yesterday, so the app would ask the API for the wrong lesson. */
export function todayIso(now: Date = new Date()): string {
  const parts = ISO_PARTS.formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** The calendar day before `iso`. Pure date arithmetic anchored at UTC noon,
 * so no timezone or DST rule can nudge it onto the wrong day. */
export function previousDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const at = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), 12));
  at.setUTCDate(at.getUTCDate() - 1);
  return at.toISOString().slice(0, 10);
}

export function yesterdayIso(now: Date = new Date()): string {
  return previousDay(todayIso(now));
}
