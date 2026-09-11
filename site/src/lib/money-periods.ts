export type MoneyBounds = {
  start?: string;
  end?: string;
  inOffice?: number;
};

export const currentMoneyCycle = (now = new Date()): number => {
  const year = Number(new Intl.DateTimeFormat("en-US", {
    year: "numeric", timeZone: "America/Chicago",
  }).format(now));
  return year + year % 2;
};

export const moneyPeriods = (now = new Date()) => {
  const current = currentMoneyCycle(now);
  const periods = [];
  for (let year = current; year >= 2008; year -= 2) {
    periods.push({
      key: String(year),
      label: `${year - 1}–${year}${year === current ? " · Current" : ""}`,
      start: `${year - 1}-01-01`, end: `${year}-12-31`,
    });
  }
  return [...periods, { key: "all", label: "All available history", start: "0000-01-01", end: "9999-12-31" }];
};

export type MoneyPeriod = ReturnType<typeof moneyPeriods>[number];
export const moneyViews = (now = new Date()) => moneyPeriods(now).flatMap((period) =>
  [false, true].map((inOffice) => ({
    period, scope: inOffice ? "office" : "all",
    bounds: { start: period.start, end: period.end, inOffice: Number(inOffice) },
    isDefault: period.key === String(currentMoneyCycle(now)) && !inOffice,
  })),
);
