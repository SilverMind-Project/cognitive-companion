/** Python weekdays, as the API sends them: 0 is Monday. */
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** The days a dose repeats, in words. */
export function formatDays(days) {
  if (days.length === WEEKDAYS.length) return "Every day";
  return [...days]
    .sort((a, b) => a - b)
    .map((day) => WEEKDAYS[day])
    .join(", ");
}
