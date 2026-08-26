/** Shared client-side list filter: query against data-text rows, with a
 * live result count and an empty state. Applies once at init (and on
 * pageshow) so a browser-restored query never shows a stale list. The
 * announcement is debounced so typing isn't drowned out; the visual
 * filtering stays immediate. Returns apply() for deep links.
 *
 * With `facetAttr`, the bar's chips single-select on data-<facetAttr> and
 * mirror into the query string, so a filtered view stays shareable and an
 * inbound ?<facetAttr>= link arrives pre-filtered. Chips never remove rows
 * from the page — they only hide them — so the full list stays in the HTML
 * and in the search index. */
export function initRowFilter(opts: {
  input: string;
  rows: string;
  status: string;
  noMatch: string;
  noun: string;
  facetAttr?: string;
  extra?: (row: HTMLElement) => boolean;
}): () => void {
  const input = document.getElementById(opts.input) as HTMLInputElement;
  const status = document.getElementById(opts.status)!;
  const noMatch = document.getElementById(opts.noMatch)!;
  const rows = document.querySelectorAll<HTMLElement>(opts.rows);
  const chips = opts.facetAttr
    ? [
        ...document.querySelectorAll<HTMLButtonElement>(
          `[data-facet-for="${opts.facetAttr}"]`,
        ),
      ]
    : [];
  let facet = opts.facetAttr
    ? (new URLSearchParams(location.search).get(opts.facetAttr) ?? "")
    : "";
  let announceTimer: ReturnType<typeof setTimeout> | undefined;

  const paintChips = () => {
    for (const chip of chips) {
      const on = (chip.dataset.facet ?? "") === facet;
      chip.setAttribute("aria-pressed", String(on));
      chip.classList.toggle("border-navy-800", on);
      chip.classList.toggle("bg-navy-800", on);
      chip.classList.toggle("text-white", on);
      chip.classList.toggle("border-navy-100", !on);
      chip.classList.toggle("bg-white", !on);
    }
  };

  const apply = () => {
    const q = input.value.toLowerCase();
    let shown = 0;
    rows.forEach((row) => {
      const hide =
        !row.dataset.text!.includes(q) ||
        (facet !== "" && row.getAttribute(`data-${opts.facetAttr}`) !== facet) ||
        !(opts.extra?.(row) ?? true);
      row.classList.toggle("sorted-hidden", hide);
      if (!hide) shown++;
    });
    const filtering = q !== "" || facet !== "" || opts.extra !== undefined;
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      status.textContent = filtering
        ? `${shown.toLocaleString()} of ${rows.length.toLocaleString()} ${opts.noun} shown`
        : `Showing all ${rows.length.toLocaleString()} ${opts.noun}.`;
    }, 500);
    noMatch.textContent = shown === 0 ? `No ${opts.noun} match "${input.value}".` : "";
    noMatch.classList.toggle("hidden", shown > 0);
  };

  for (const chip of chips) {
    chip.addEventListener("click", () => {
      const key = chip.dataset.facet ?? "";
      facet = key === facet ? "" : key;
      const url = new URL(location.href);
      if (facet) url.searchParams.set(opts.facetAttr!, facet);
      else url.searchParams.delete(opts.facetAttr!);
      history.replaceState(null, "", url);
      paintChips();
      apply();
    });
  }

  input.addEventListener("input", apply);
  window.addEventListener("pageshow", () => {
    if (input.value) apply();
  });
  paintChips();
  if (input.value || facet) apply();
  return apply;
}
