/** As-you-type address suggestions from Google Places (New), attached as
 * a progressive enhancement: with no key, or when Google is unreachable,
 * the plain input keeps working and the submitted address still resolves
 * through the Census geocoder. Wisconsin-restricted, three characters
 * and a 250 ms pause before a request, one session token per pick so
 * Google bills the burst as one autocomplete session. */
import { esc } from "../lib/html";
import { PLACES_KEY } from "./../lib/placesKey";

const ENDPOINT = "https://places.googleapis.com/v1/places:autocomplete";
const WISCONSIN = {
  rectangle: {
    low: { latitude: 42.49, longitude: -92.9 },
    high: { latitude: 47.1, longitude: -86.8 },
  },
};

export function attachSuggest(input: HTMLInputElement, onPick?: () => void): void {
  if (!PLACES_KEY) return;
  const wrap = document.createElement("div");
  wrap.className = "relative min-w-0 flex-1";
  input.parentElement!.insertBefore(wrap, input);
  wrap.appendChild(input);
  input.classList.remove("flex-1");
  input.classList.add("w-full");
  const list = document.createElement("ul");
  list.id = `${input.id}-suggest`;
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Address suggestions");
  list.className =
    "absolute z-30 mt-1 hidden max-h-64 w-full overflow-y-auto rounded-lg border border-navy-100 bg-white text-left text-sm shadow-lg";
  wrap.appendChild(list);
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("autocomplete", "off");

  let items: string[] = [];
  let active = -1;
  let session = crypto.randomUUID();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let seq = 0;

  const close = () => {
    items = [];
    active = -1;
    list.innerHTML = "";
    list.classList.add("hidden");
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  const paint = () => {
    list.innerHTML = items
      .map(
        (t, i) =>
          `<li id="${list.id}-${i}" role="option" aria-selected="${i === active}"
             class="cursor-pointer px-3 py-2 ${i === active ? "bg-navy-50" : ""}">${esc(t)}</li>`,
      )
      .join("");
    list.classList.toggle("hidden", items.length === 0);
    input.setAttribute("aria-expanded", String(items.length > 0));
    if (active >= 0) input.setAttribute("aria-activedescendant", `${list.id}-${active}`);
    else input.removeAttribute("aria-activedescendant");
  };
  const pick = (i: number) => {
    if (items[i] == null) return;
    input.value = items[i].replace(/, USA$/, "");
    close();
    session = crypto.randomUUID();
    onPick?.();
  };
  const suggest = async () => {
    const q = input.value.trim();
    if (q.length < 3) return close();
    const mine = ++seq;
    try {
      const r = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Goog-Api-Key": PLACES_KEY,
          "X-Goog-FieldMask": "suggestions.placePrediction.text.text",
        },
        body: JSON.stringify({
          input: q,
          sessionToken: session,
          includedRegionCodes: ["us"],
          locationRestriction: WISCONSIN,
        }),
      });
      if (mine !== seq) return;
      if (!r.ok) return close();
      const data = await r.json();
      items = ((data.suggestions ?? []) as { placePrediction?: { text?: { text?: string } } }[])
        .map((s) => s.placePrediction?.text?.text)
        .filter((t): t is string => !!t)
        .slice(0, 6);
      active = -1;
      paint();
    } catch {
      close();
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(suggest, 250);
  });
  input.addEventListener("keydown", (e) => {
    if (list.classList.contains("hidden")) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      active = (active + 1) % items.length;
      paint();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      active = (active - 1 + items.length) % items.length;
      paint();
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(active);
    } else if (e.key === "Escape") {
      close();
    }
  });
  list.addEventListener("mousedown", (e) => {
    const li = (e.target as HTMLElement).closest("li[role=option]");
    if (li) {
      e.preventDefault();
      pick([...list.children].indexOf(li));
    }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}
