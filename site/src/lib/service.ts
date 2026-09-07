/** Pure service-span and attendance derivations; no database access. */
import { OPEN_END } from "./sentinels";

export interface TermRow {
  chamber: string;
  district: number | null;
  start: string;
  end: string | null;
  end_label: string | null;
  end_url: string | null;
}

export interface HeatDay {
  date: string;
  total: number;
  cast: number;
  nv: number;
  served: boolean;
}

/** Merge terms across biennium boundaries while preserving longer service gaps. */
export const mergeServiceSpans = (terms: TermRow[]): TermRow[] => {
  const spans: TermRow[] = [];
  for (const t of [...terms].sort((a, b) => a.start.localeCompare(b.start))) {
    const prev = spans[spans.length - 1];
    const gapDays =
      prev?.end ? (Date.parse(t.start) - Date.parse(prev.end)) / 86400000 : Infinity;
    if (prev && prev.chamber === t.chamber && prev.district === t.district && gapDays <= 45) {
      prev.end = t.end;
      prev.end_label = t.end_label;
      prev.end_url = t.end_url;
    } else {
      spans.push({ ...t });
    }
  }
  return spans;
};

/** Count votes only during service in that chamber. Keep zeroed non-service
 * days in the heatmap so they appear as "not in office", not missed votes. */
export const buildHeatDays = (
  terms: TermRow[],
  mine: { date: string; chamber: string; cast: number; nv: number }[],
  chamberDays: { chamber: string; date: string; n: number }[],
): HeatDay[] => {
  const heatDays: HeatDay[] = [];
  for (const chamber of ["lower", "upper"] as const) {
    const chamberTerms = terms.filter((t) => t.chamber === chamber);
    if (!chamberTerms.length) continue;
    // Term ends are inclusive; a same-day chamber transfer belongs only
    // to the incoming chamber, avoiding false absences in the outgoing one.
    const handover = (t: TermRow) =>
      t.end != null && terms.some((o) => o.chamber !== t.chamber && o.start === t.end);
    const inTerm = (date: string) =>
      chamberTerms.some(
        (t) =>
          date >= t.start &&
          (handover(t) ? date < (t.end ?? OPEN_END) : date <= (t.end ?? OPEN_END)),
      );
    const spanStart = chamberTerms[0].start;
    const spanEnd = chamberTerms.reduce(
      (max, t) => ((t.end ?? OPEN_END) > max ? (t.end ?? OPEN_END) : max), "0");
    const myByDate = new Map(
      mine.filter((m) => m.chamber === chamber).map((m) => [m.date, m]),
    );
    for (const day of chamberDays.filter((c) => c.chamber === chamber)) {
      if (day.date < spanStart || day.date > spanEnd) continue;
      const served = inTerm(day.date);
      const m = myByDate.get(day.date);
      heatDays.push({
        date: day.date, total: day.n,
        cast: served ? (m?.cast ?? 0) : 0, nv: served ? (m?.nv ?? 0) : 0, served,
      });
    }
  }
  return heatDays;
};
