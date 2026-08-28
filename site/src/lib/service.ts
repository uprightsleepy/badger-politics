/** Pure service-history derivations for legislator profiles — span
 * merging and the attendance heatmap's in-office gating. No DB access,
 * so the recall/resignation rules stay unit-testable. */
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

/** Merge biennium-boundary term rows for display; real gaps (recalls,
 * comebacks) are months long and stay visible. */
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

/** A chamber's voting day counts only when it falls inside one of this
 * person's recorded service terms for that chamber. Out-of-office days
 * within the overall span are kept (zeroed) so a mid-year exit shows as
 * "not in office", never as missed votes. */
export const buildHeatDays = (
  terms: TermRow[],
  mine: { date: string; chamber: string; cast: number; nv: number }[],
  chamberDays: { chamber: string; date: string; n: number }[],
): HeatDay[] => {
  const heatDays: HeatDay[] = [];
  for (const chamber of ["lower", "upper"] as const) {
    const chamberTerms = terms.filter((t) => t.chamber === chamber);
    if (!chamberTerms.length) continue;
    // A term's end date is inclusive: members do cast votes on their last
    // day, 117 of them on record. The exception is a member who moves
    // between chambers, where one term ends and the next begins on the
    // same date. Counting both left them sitting in the chamber they had
    // just left, so the chamber's votes that day showed as missed. Dan
    // Knodl's Senate term ended and his Assembly term began on 2025-01-06,
    // which gave him two tiles for that day and two phantom absences. No
    // member has ever voted in the chamber they were leaving on such a
    // day, so the ending term simply does not claim it.
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
