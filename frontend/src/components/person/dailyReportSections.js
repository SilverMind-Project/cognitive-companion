/**
 * The daily report's sections, turned from the backend's aggregates into labelled rows. Each row
 * is what a caregiver reads: plain words and real units, never a field name.
 *
 * Medication shows doses and how each was confirmed. It leaves out `doses_due` and `adherence_pct`
 * because `doses_due` is still a backend placeholder, so that percentage means nothing yet.
 */

/** Minutes as "7 h 32 min", or "45 min" under an hour. */
export function formatMinutes(minutes) {
  const total = Math.round(minutes);
  if (total < 60) return `${total} min`;
  const remainder = total % 60;
  return remainder ? `${Math.floor(total / 60)} h ${remainder} min` : `${total / 60} h`;
}

const count = (label, value) => ({
  label,
  value: value == null ? null : String(value),
  raw: value,
});
const duration = (label, value) => ({
  label,
  value: value == null ? null : formatMinutes(value),
  raw: value,
});
const percent = (label, fraction) => ({
  label,
  value: fraction == null ? null : `${Math.round(fraction * 100)}%`,
  raw: fraction,
});

/** The rows worth showing: a section where nothing happened reads "No data". */
function present(rows) {
  const filled = rows.filter((row) => row.value !== null);
  return filled.some((row) => row.raw) ? filled : [];
}

/** Wellness is scored 0 to 100. */
export function wellnessColor(score) {
  if (score >= 80) return "success";
  if (score >= 50) return "warning";
  return "error";
}

export function reportSections(report) {
  if (!report) return [];
  const { sleep = {}, meals = {}, medication = {}, exercise = {}, tv = {} } = report;
  const bathroom = report.bathroom_visits ?? {};
  const rooms = Object.entries(report.room_time?.distribution ?? {}).sort((a, b) => b[1] - a[1]);
  const sections = [
    {
      key: "sleep",
      label: "Sleep",
      icon: "mdi-bed",
      rows: [
        duration("Total sleep", sleep.total_minutes),
        count("Sleep periods", sleep.session_count),
        count("Disruptions", sleep.disruptions),
        percent("Of 8-hour target", sleep.quality_score),
      ],
    },
    {
      key: "meals",
      label: "Meals",
      icon: "mdi-silverware",
      rows: [
        count("Meals prepared", meals.prep_count),
        count("Meals eaten", meals.eating_count),
        duration("Average length", meals.avg_duration_minutes),
      ],
    },
    {
      key: "medication",
      label: "Medication",
      icon: "mdi-pill",
      rows: [
        count("Doses taken", medication.doses_taken),
        count("Confirmed in a routine", medication.confirmed_doses),
        count("Inferred from camera", medication.inferred_doses),
      ],
    },
    {
      key: "bathroom_visits",
      label: "Bathroom",
      icon: "mdi-toilet",
      rows: [
        count("Visits", bathroom.visit_count),
        duration("Total time", bathroom.total_minutes),
        duration("Average visit", bathroom.avg_duration_minutes),
      ],
    },
    {
      key: "exercise",
      label: "Exercise",
      icon: "mdi-run",
      rows: [
        count("Sessions", exercise.session_count),
        duration("Total time", exercise.total_minutes),
      ],
    },
    {
      key: "tv",
      label: "Watching TV",
      icon: "mdi-television",
      rows: [count("Sessions", tv.session_count), duration("Total time", tv.total_minutes)],
    },
    {
      key: "room_time",
      label: "Time by room",
      icon: "mdi-floor-plan",
      rows: rooms.map(([room, minutes]) => duration(room, minutes)),
    },
  ];
  return sections.map((section) => ({
    ...section,
    rows: present(section.rows).map(({ label, value }) => ({ label, value })),
  }));
}
