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
