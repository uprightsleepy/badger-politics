/** Synchronize chip styling and pressed state with the selected facets. */
export const paintChips = (
  chips: HTMLButtonElement[],
  isOn: (chip: HTMLButtonElement) => boolean,
): void => {
  for (const chip of chips) {
    const on = isOn(chip);
    chip.setAttribute("aria-pressed", String(on));
    chip.classList.toggle("border-navy-800", on);
    chip.classList.toggle("bg-navy-800", on);
    chip.classList.toggle("text-white", on);
    chip.classList.toggle("border-navy-100", !on);
    chip.classList.toggle("bg-white", !on);
  }
};

/** Filter rows in place, sync the query and facets to the URL, and debounce count
 * announcements. Reapply on pageshow; return apply() for deep links. */
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
  const clear = document.querySelector<HTMLButtonElement>(`[data-filter-clear="${opts.input}"]`);
  input.value = new URLSearchParams(location.search).get("q") ?? input.value;
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

  const paint = () => paintChips(chips, (chip) => (chip.dataset.facet ?? "") === facet);

  const apply = () => {
    const url = new URL(location.href);
    if (input.value) url.searchParams.set("q", input.value);
    else url.searchParams.delete("q");
    if (opts.facetAttr) {
      if (facet) url.searchParams.set(opts.facetAttr, facet);
      else url.searchParams.delete(opts.facetAttr);
    }
    history.replaceState(null, "", url);
    clear?.classList.toggle("hidden", !input.value && !facet);
    const rows = document.querySelectorAll<HTMLElement>(opts.rows);
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
    const filtering = shown !== rows.length;
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
      paint();
      apply();
    });
  }

  input.addEventListener("input", apply);
  clear?.addEventListener("click", () => {
    input.value = "";
    facet = "";
    paint();
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  });
  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(location.search);
    input.value = params.get("q") ?? "";
    facet = opts.facetAttr ? params.get(opts.facetAttr) ?? "" : "";
    paint();
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  window.addEventListener("pageshow", () => {
    if (input.value) apply();
  });
  paint();
  if (input.value || facet) apply();
  return apply;
}
