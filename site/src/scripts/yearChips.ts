/** Year chips over a complete list: single-select, hiding rows of other
 * years (data-y). No query-string sync; a page can hold several groups. */
import { paintChips } from "./rowFilter";

for (const bar of document.querySelectorAll<HTMLElement>("[data-yearchips]")) {
  const list = document.getElementById(bar.dataset.yearchips!);
  if (!list) continue;
  const chips = [...bar.querySelectorAll<HTMLButtonElement>("button[data-year]")];
  let year = "";
  bar.addEventListener("click", (e) => {
    const chip = (e.target as HTMLElement).closest<HTMLButtonElement>("button[data-year]");
    if (!chip) return;
    year = chip.dataset.year === year ? "" : (chip.dataset.year ?? "");
    paintChips(chips, (c) => (c.dataset.year ?? "") === year);
    for (const row of list.querySelectorAll<HTMLElement>("[data-y]")) {
      row.classList.toggle("sorted-hidden", year !== "" && row.dataset.y !== year);
    }
  });
}
