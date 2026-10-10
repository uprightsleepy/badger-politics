# Badger Politics brand guidelines

*Proposed October 2026 in the redesign's Phase 3. Once approved, this replaces the palette comment in
`site/src/styles/global.css` as the source of truth for how the site looks and talks.*

Badger Politics exists so someone with no civics background can land on any page and understand what
they're looking at within a few seconds. It should feel like a calm, well-made consumer product, the
kind of thing you'd use to track a package or read a lab result. It should not feel like a news site or
a campaign.

## Direction: follow the route

The Legislature is a route, and every bill travels it: introduced, committee, a vote in each chamber,
the governor, law. Most bills stop somewhere along the way. The site works like good public
wayfinding. Every page answers three questions before anything else:

1. Where is it?
2. Who has it now?
3. What happens next?

The **route** is the one memorable element. It's a line with stops, already-traveled road in Lake,
the road ahead dashed, and the current stop marked with a Prairie "you are here" ring. It appears on bill
pages, in lists of bills, and anywhere a bill's progress is summarized. Everything around it stays quiet.

The type comes from the same idea. Headings and numbers are set in Overpass, which is drawn from Highway
Gothic, the lettering on Wisconsin road signs. Reading text is set in Atkinson Hyperlegible Next, which
the Braille Institute designed so that people with low vision can tell every letter apart.

### What we are not

- **Not a news site.** No masthead bar, no headline feed, no "latest" ticker, no desk names like
  "Tracker" or "Desk", no Title Case headlines, no all-caps labels.
- **Not red versus blue.** No red, no blue and no purple anywhere in the brand.
- **Not alarming.** No urgency cues, no "graveyard", no "This bill is dead." A bill that stopped is
  described plainly, the same way a delayed package is.

## Principles

1. **Answer first.** The first screen of every page states where things stand in one sentence. Detail
   follows; methodology goes last.
2. **Color only ever means "look here".** It never means good or bad, and never a party.
3. **Plain words first, official words a tap away.** Every term of art has a plain label, and the
   official term lives in its definition.
4. **Every number has a yardstick.** A count comes with what it's out of, what's typical, or what it
   changed from.
5. **Party is a word.** Written out ("Republican", "Democrat"), the same size and color as the text
   around it.
6. **Say what's missing, once.** Never show a gap as a zero. One "What these numbers include" note per
   page, not a caveat under every figure.

## Color

| Token | Hex | Role | Contrast |
| --- | --- | --- | --- |
| `limestone` | `#F4F6F2` | Page ground | — |
| `white` | `#FFFFFF` | Raised sheets: status, forms, people | — |
| `spruce` | `#18241F` | Text, headings, the "you are here" ring | 14.7:1 on limestone, 16.0:1 on white |
| `granite` | `#55605A` | Secondary text: dates, captions, sources | 6.0:1 on limestone, 6.6:1 on white |
| `lake` | `#0D5C63` | Links, primary buttons, focus ring, road already traveled | 7.1:1 on limestone, 7.7:1 on white; white on lake 7.7:1 |
| `prairie` | `#F2C34F` | "Look here": the current stop, your lawmakers, your district | Spruce on prairie 9.7:1 |
| `prairie-tint` | `#FCF1CF` | Background of "you" notes and the district chip | Spruce on it 14.2:1 |
| `edge` | `#848E88` | Control borders, road ahead (dashed), unreached stops | 3.4:1 on white, 3.1:1 on limestone |
| `rule` | `#D6DCD7` | Hairlines between sections and rows (decorative) | — |
| `fog` | `#E6EBE7` | Neutral fills: tracks, map land, placeholders | Spruce on fog 13.3:1 |
| `lake-tint` | `#B9D3D2` | The "typical range" band on range bars | — |

Rules:

- **Prairie is never text** (1.7:1 on white). It's a fill behind Spruce text, or a ring with a Spruce border.
- **Only one thing per screen gets Prairie**: the current stop, or the reader's own lawmakers and district.
- **No status colors.** Outcomes (became law, vetoed, stopped) are told apart by words and the route's
  shape, not by green and red.
- **Data graphics** use Lake, Spruce, Granite and Fog, separated by lightness. Prairie marks the
  reader's own item. A third series or more gets a pattern or direct labels, never a party color.
- **Maps** use Fog for land, white for borders, Prairie for the reader's district, and a Lake outline
  for the larger district around it.

## Typography

Both families are self-hosted variable fonts, latin subset, about 73 KB together, loaded with
`font-display: swap` and preloaded:

- **Overpass** (`@fontsource-variable/overpass@5.3.0`, OFL): headings, numbers, route labels, buttons,
  wordmark.
- **Atkinson Hyperlegible Next** (`@fontsource-variable/atkinson-hyperlegible-next@5.3.0`, OFL):
  everything you read.
- **Fallback**: `system-ui, sans-serif`.

| Style | Family | Size / line height | Weight | Use |
| --- | --- | --- | --- | --- |
| Display | Overpass | 39 / 43 px (31 / 36 on phones) | 800 | Page title |
| Status | Overpass | 31 / 34 px (25 / 29 on phones) | 800 | "Stopped in committee" |
| Section | Overpass | 25 / 30 px (22 / 27 on phones) | 700 | Section headings |
| Question | Overpass | 17 / 22 px | 700 | Questions on profiles, route stop names |
| Body | Atkinson | 17 / 26 px | 400 | All reading text |
| Lead | Atkinson | 19 / 29 px | 400 | First paragraph under a title |
| Small | Atkinson | 15 / 22 px | 400 | Captions, help text |
| Fine | Atkinson | 13–14 / 20 px | 400 | Sources, scale labels. Never smaller |
| Figure | Overpass | inherit | 700 | Numbers inside sentences, `tabular-nums` |

Rules:

- **Case:** sentence case everywhere. No all caps, no letter-spaced eyebrow labels.
- **Line length:** no more than about 70 characters (`max-width: 720px` for reading text).
- **Size:** nothing smaller than 13 px, and anything a reader must act on is 15 px or larger.

## Space, shape and layout

- **Spacing:** a 4 px base with steps of 4, 8, 12, 16, 20, 24, 32, 40, 56 and 72.
- **Page widths:** pages are at most 1160 px wide. Reading columns are at most 720 px. The phone
  gutter is 20 px.
- **Mobile first:** one column on phones. From about 1000 px, bill pages and lawmaker pages add a 300–360 px
  side rail for actions, "your representative" and "Terms on this page".
- **Separation:** sections are separated by 32–40 px of space and a `rule` hairline, not by boxes. Only
  three things are raised sheets on white: the status block, forms, and person cards.
- **Radius by hierarchy:**
  - Sheets: 16 px
  - Maps and images: 12 px
  - Controls and buttons: 10 px
  - Chips: fully round
- **Shadows:** none, except one soft shadow on menus and popovers that float over content.

## Iconography

- **Drawing:** line icons on a 24 px grid, 2 px stroke, round caps and joins, `currentColor`, drawn
  inline as SVG.
- **The set:** search, menu, follow (bookmark), mail, phone, location pin, lock, calendar,
  external link, plus and minus. Add an icon only when a word alone would be slower to read.
- **Never:** emoji, icon fonts, or arrows appended to link text.

## Mark and wordmark

- **The mark:** the Wisconsin silhouette in Spruce with a Prairie dot where the Capitol sits in
  Madison. It's the brand's "you are here".
- **The wordmark:** "Badger Politics" in Overpass 800.
- **On dark grounds:** the silhouette turns Limestone and the dot stays Prairie.
- **Size and spacing:** the mark is at least 24 px tall, with clear space equal to the dot's diameter
  on every side.
- **Retired:** the gold silhouette (`wisconsin.svg`). The source file for the new mark is generated
  from the Legislature's district boundaries (`site/src/data/district-shapes.json`).

## Components

### Route (bill progress)

Replaces the stepper. Stops for a bill are Introduced, Committee, a vote in the chamber it started in, a
vote in the other chamber, Governor, Law. A resolution's route ends at Adopted.

- **States:**
  - Traveled: a filled Lake dot and a solid Lake line.
  - Current or stopped: a Prairie ring with a 3 px Spruce border.
  - Not reached: a hollow dot with an Edge border and a dashed Edge line.
- **Labels:** the current stop gets a sentence ("Stopped here. No hearing was scheduled."). The stops
  around it get only their name and date.
- **Layout:** vertical in narrow spaces, horizontal once the route's own container is 34rem (544 px)
  wide, so it works the same in the status block and anywhere else it appears.
- **Markup:** an `<ol>` with each stop's state in text, for example a visually hidden ", not reached".
  It must work in forced-colors mode.
- **The stopping point is honest:** a bill that never got a hearing stops at Committee, not at
  Introduced.

### Bill rows

Every list of bills uses one row (`site/src/components/BillList.astro`):

1. The bill number and its official title, as one link. The whole row is the link's target.
2. A small route (dots only, hidden from screen readers) and the same status headline the bill's own
   page shows, then "Last action" and its date.

The headline comes from the same code as the bill page (`lib/billRows.ts` calls `tellStory`), so a
list and a page never describe a bill two ways.

### Chips

Views and filters are chips: fully round, a 2 px Edge border, at least 44 px tall. The chosen one is
filled Spruce with white text, marked with `aria-current` (a link to a view) or `aria-pressed` (a
toggle). Counts sit inside the chip in regular weight.

### Status block

A white sheet at the top of every bill page:

1. A status headline (see Status wording).
2. One to three sentences: where it is, who decides, what happens next and by when.
3. The route.
4. One line of fine print with the official wording, for example "Failed to pass pursuant to Senate
   Joint Resolution 1", with its term linked.

### Header

- **Desktop:** white, two quiet rows. First the mark and wordmark, search, and the "Your districts" chip
  (or "Find your lawmakers" before an address is saved). Then the sections: Bills, Lawmakers, Money,
  Calendar, Elections, Following.
- **Phones:** mark, a search button and Menu. Once an address is saved, the districts chip sits under
  the bar.
- **Section names** are plain: "All bills", "New laws", "Bills by subject", "Governor's decisions",
  "Vetoes", "Bills that never got a hearing", "State lawmakers", "Members of Congress", "City councils",
  "Campaign money", "Outside spending".

### "You are here" highlight

- A Prairie-tint chip in the header, "Your districts: Assembly 14, Senate 5", once the reader has saved
  an address.
- A Prairie-tint note wherever their lawmakers appear ("Your representative, Angelito Tenorio, is one of
  this bill's 25 authors.").

Nothing else uses Prairie.

### Buttons and links

- **Primary:** Lake fill with white text, at most one per view.
- **Secondary:** white with a 2 px Edge border.
- **Size:** at least 44 px tall, 48 px on phones.
- **Links:** Lake and always underlined.
- **Labels** say exactly what happens, and an action keeps its name: "Follow this bill" becomes
  "Following".

### Terms (inline definitions)

- **In the text:** a term of art gets a dotted Granite underline the first time it appears on a page.
  Activating it opens its definition: a bottom sheet on phones, a small card on wider screens. It's a
  native `popover`, so it needs no script. The card gives the plain name, a one-sentence definition,
  "Official term" and a link to the glossary.
- **At the foot of the page:** bill, lawmaker and money pages end with "Terms on this page", generated
  from the terms the page used.
- **One source:** the glossary is the single source of every definition (`site/src/lib/glossary.ts`):
  full entries for the glossary page, short plain ones for "Terms on this page".

### Range bar (a value against what's typical)

A Fog track with a `lake-tint` band for the middle half of the chamber and a Spruce marker for this
person. The sentence above it gives the number ("Missed 0 of 245 votes this session"). The label below
names the typical range in words. Ranges are computed at build time from data the site already has.

### Person card

Used on My reps and lawmaker pages:

1. Portrait or silhouette, the name, then "Your representative in the Assembly. Democrat."
2. Email and Call buttons.
3. Plain questions, each answered in a sentence:
   - Do they show up to vote?
   - How often do they vote with their party?
   - What have they tried to pass?
   - Are they on your ballot?
   - How did they vote most recently?

### History list

- **Order:** newest first, each event a plain sentence with its date.
- **Grouping:** repeated events (coauthors added) collapse into one line ("8 more representatives and 2
  senators signed on").
- **The clerk's log** stays one link away: "See the official record, word for word".

### Split bar

Two-sided tallies (Yes against No, two-candidate results) use one bar in Spruce and Fog with both
numbers at its ends. The winner is named in words.

## Words

### Reading level and voice

- **Reading level:** everything we write reads at grade 8 or below (Flesch-Kincaid), with most
  sentences under 20 words.
- **Official text stays verbatim:** the Legislative Reference Bureau's summaries and bill titles are
  never rewritten, and they're labelled with who wrote them.
- **Voice:** second person ("your representative"), active voice, sentence case.
- **Tone:** no exclamation marks, no emoji, no sarcasm.
- **Calm about failure:** a bill that failed "stopped" or "died when the session ended". It is never
  "killed", "buried" or in a "graveyard".

### Plain words for official terms

| Official | We say | Official term kept in |
| --- | --- | --- |
| AB 656 | Assembly Bill 656 (AB 656 in tight lists) | — |
| AD 14 / SD 5 | Assembly District 14 / Senate District 5 | — |
| Aye / Nay / NV | Yes / No / Didn't vote | Roll-call detail |
| Concurrence | The second chamber's vote | Definition |
| Referred to committee | Sent to the Committee on … | History detail |
| Failed to pass pursuant to SJR 1 | Stopped: the session ended | Status block fine print |
| Floorperiod | Voting days | Definition |
| Canvass | Official count | Definition |
| Approved for ballot access | Qualified for the ballot | Definition |
| Per diem | Daily expense pay | Definition |
| Coauthor / cosponsor | Signed on in support | Definition |
| Atom feed / .ics | Get updates in a feed reader / Add to your calendar | Help text |

### Status wording

Headlines are what the reader needs to know, not the clerk's state.

| Data status | While the session is open | After the session ends |
| --- | --- | --- |
| `introduced`, `in_committee` | **Waiting in committee.** "The Committee on … has it. It needs a hearing before it can move." | **Stopped in committee.** "It never got a public hearing" (or "It had a hearing but no vote") "so it never came up for a vote." |
| `passed_chamber` | **Passed the Assembly.** "It's waiting for the Senate." | **Passed the Assembly, then stopped.** "The Senate never voted on it before the session ended." |
| `passed` | **Waiting for the governor.** "Both chambers passed it. The governor can sign or veto it." | — |
| `enacted` | **Became law.** "Signed on [date]. It's Wisconsin Act [n]." | same |
| `vetoed` | **Vetoed by the governor.** "Both chambers passed it, and the governor rejected it on [date]." | same, plus the override result |
| `adopted` (resolutions) | **Adopted.** "Resolutions don't go to the governor." | same |
| `failed_sjr1` | — | As `in_committee` or `passed_chamber`, whichever matches where it was |

### Numbers

- **Give a yardstick:** "Missed 0 of 245 votes. Most representatives missed between [x] and [y]." A
  bare number is a bug.
- **Money:** whole dollars, rounded once it's large ("$10.5 million"), exact in the table beneath.
- **Percentages:** always say the base: "90% of 239 votes in 2025".
- **Dates:** "Mar 19, 2026" in lists and "March 19, 2026" in sentences. Use "Tomorrow" and "Next
  Tuesday" for what's coming up.
- **Party totals:** never compare one party's totals with the other's unless both are fully covered.
  Coverage gaps are stated in words, never shown as zero.

### Party and neutrality

- **The word, never a color:** party is the word Republican or Democrat. Independents and others get
  their party's name.
- **Abbreviations:** "(R)" and "(D)" only in dense lists, and only with a key on the same screen.
- **No colored chips,** and no party coding in charts or maps.
- **Rankings:** every ranking says what it measures and what it doesn't.
- **Ordering:** party never orders a list. Lists go alphabetically, by district or by date.

## Accessibility

The baseline is WCAG 2.2 AA, checked with axe in `site/scripts/a11y.mjs` plus a manual pass.

- **Contrast:** text is at least 4.5:1, or 3:1 at 24 px and up. Control borders, focus rings and
  meaningful marks are at least 3:1. The contrast column above covers every pairing.
- **Focus:** a 3 px Lake outline with a 2 px offset, on every interactive element.
- **Targets:** at least 44 by 44 px.
- **Names:** the route, range bars and maps carry a text equivalent. Icon-only buttons have an
  `aria-label`.
- **Forced colors:** the route, buttons and chips keep their borders in Windows High Contrast.
- **Motion:** nothing moves on its own. Smooth scrolling only runs without `prefers-reduced-motion`.

## Performance

- **Fonts:** two preloaded variable font files, about 73 KB.
- **Icons:** inline SVG, no icon requests.
- **No new client JavaScript for presentation.** Popovers for terms use `<details>` or the native
  `popover` attribute.
- **Pages are static HTML:** status, route and history render with no script.

## What changes from today

| Today | New |
| --- | --- |
| `navy-*`, `badger-*`, `gold-*`, `moss-*` theme colors | The tokens above. `badger-*` and `moss-*` are retired |
| `PartyChip` (colored R/D circle) | The party written out |
| `StatusBadge` colored pills | Status headline and route |
| `Stepper` (✕ on Introduced for committee deaths) | Route with an honest stopping point |
| Navy masthead with gold call-to-action | White header, search, "Your districts" chip |
| "Hearing: None", "Veto Tracker", "The Governor's Desk", "Civic Calendar" | Plain names, for example "Bills that never got a hearing", "Vetoes", "Governor's decisions", "Calendar" (URLs may change later, with redirects) |
| Gold silhouette mark | Spruce silhouette with a Prairie Capitol dot |
| Homepage flow diagram (colored ribbons) | One list of outcomes in route order, each with a count, its share and a Lake bar |
| System font only | Overpass and Atkinson Hyperlegible Next, self-hosted |

## Rolling it out

The redesign ships one page type at a time. Until a page type is redone:

- **Legacy color names** (`navy-*`, `gold-*`, `badger-*`, `moss-*`, `paper`, `ink`) are mapped onto this
  palette in `global.css`, so older pages already use the new colors without red, blue or party hues.
  Each name is removed once nothing uses it.
- **Redesigned pages** opt into the new frame with `<Base layout="wide">` (1160 px, wider gutters).
  Others keep the original 1024 px column.
- **Shared pieces** (header, footer, fonts, party and status chips, roll calls, follow buttons) are
  already new everywhere.
