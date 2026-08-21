/** Shared client-side list filter: query against data-text rows, with a
 * live result count and an empty state. Returns apply() for deep links. */
export function initRowFilter(opts: {
  input: string;
  rows: string;
  status: string;
  noMatch: string;
  noun: string;
  extra?: (row: HTMLElement) => boolean;
}): () => void {
  const input = document.getElementById(opts.input) as HTMLInputElement;
  const status = document.getElementById(opts.status)!;
  const noMatch = document.getElementById(opts.noMatch)!;
  const apply = () => {
    const q = input.value.toLowerCase();
    const rows = document.querySelectorAll<HTMLElement>(opts.rows);
    let shown = 0;
    rows.forEach((row) => {
      const hide = !row.dataset.text!.includes(q) || !(opts.extra?.(row) ?? true);
      row.classList.toggle("sorted-hidden", hide);
      if (!hide) shown++;
    });
    const filtering = q !== "" || opts.extra !== undefined;
    status.textContent = filtering ? `${shown} of ${rows.length} ${opts.noun} shown` : "";
    noMatch.textContent = shown === 0 ? `No ${opts.noun} match "${input.value}".` : "";
    noMatch.classList.toggle("hidden", shown > 0);
  };
  input.addEventListener("input", apply);
  return apply;
}
