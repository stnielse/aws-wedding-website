# Design artifacts — Kaitlyn & Steven, 23 May 2027

Output of the mid-build design spin. Three artifacts, plus the reasoning behind
every decision so the Phase 2 build doesn't have to guess.

| File | What it is |
| --- | --- |
| `Style Guide.dc.html` | Tokens (color, type, space, radius, elevation), site structure, component specs, imagery rules, open product questions |
| `Home Page.dc.html` | Full home page mock — hero → story → the day → travel → photos teaser → RSVP band → registry + FAQ → footer |
| `RSVP.dc.html` | `/rsvp` in four states: code lookup, empty form, validation errors, submitted receipt |
| `support.js` | Runtime that renders the `.dc.html` files. Keep it in this folder or they open blank. Not part of the deliverable — do not port it. |

Open any `.dc.html` directly in a browser. The markup between `<x-dc>` and
`</x-dc>` is plain HTML with literal hex values — that's the thing to port.

---

## Scope: what got designed, what didn't

Per the brief. Designed: design system, home page, RSVP landing with all states.
Deliberately **not** designed: full gallery page (upload UX, lightbox,
pagination), travel/registry/FAQ as standalone pages beyond nav-link treatment,
admin UI, transactional emails. The gallery and travel pages have nav entries and
a home-page teaser so the information architecture is complete, but their interiors
wait for Phase 2 to exercise the models.

---

## Site structure

**Five URLs, hybrid model.**

```
/            Home — hero, our story (#story), the day (#day), travel summary
             (#travel), photos teaser (#photos), RSVP band (#rsvp),
             registry (#registry), FAQ (#faq)
/rsvp        Code lookup → form. The one URL printed on paper.
/travel      HotelBlock rows in full — rate, code, cutoff, notes, directions
/registry    RegistryLink list, outbound
/gallery     Photo grid — deferred
```

**Why a scrolling home page instead of a page per section.** A wedding site gets
read once, on a phone, by someone looking for one fact — when, where, what do I
wear, where do I sleep. Tabs and deep nav hide those facts behind a decision and
give no sense of how much there is to read. A single scroll answers everything in
one gesture; the four things a guest needs to *do* still get real URLs because
those are the ones that get texted, QR-coded, and printed.

**Why five nav items and no hamburger.** Five short labels wrap into two rows on a
320px phone without a menu button. A hamburger costs a tap, hides the RSVP call to
action, and needs JS — which the brief rules out of the design.

**Why the nav isn't sticky over the hero.** The hero is the emotional moment and
the only full-bleed photo above the fold; a bar across it competes. The nav
appears as a slim sticky bar once the hero scrolls past, with RSVP as the sole
filled button so the primary action is always one tap away. **The stickiness is
CSS (`position: sticky`) but the "appears after the hero" behavior is the build's
job** — in the mock the bar simply sits below the hero.

**Why FAQ and Our Story are anchors, not pages.** Both are short and both are read
in the flow of the page, but people link to them ("see the FAQ") — anchors give a
linkable URL without a page's worth of chrome.

**Why the footer repeats every link.** It's the second-chance nav for anyone who
scrolled past what they wanted, and it re-states the date and venue, which is the
single most-screenshotted fact on the site.

---

## Color

Values, names, and contrast ratios are in the style guide. The reasoning:

**Evergreen is the anchor** because the save-the-date already used darker greens —
guests will have seen it, and the site should feel like the same envelope. Greens
do structure (dark section bands, buttons, headings) and go nearly black at
`forest-900` so full-bleed photo scrims read as *deep forest*, not grey.

**Warm neutrals, not white.** `cream-50 #FDFBF7` and `cream-100 #F7F2E9` instead of
`#FFFFFF`. Pure white next to saturated green reads clinical; a cream base reads
like paper and matches the "warm, magical, loving" direction. Text neutrals are
warm too (`ink-700 #3D392F`, not a neutral grey) so nothing on the page fights the
temperature.

**Gold is rationed.** `gold-500 #B78B48` appears only as eyebrow labels, hairline
rules, hover states, and the one button on the dark RSVP band. It is
**3.4:1 on cream** — large text and non-text only, never body copy; that
constraint is why it's an accent and not a second brand color. Large fills of gold
are what makes a site look like a wedding-template; a thin line of it looks like
letterpress.

**`dusk-300 #E4C4B4` is optional and currently unused.** It's in the palette as a
blush wash if a section ever needs a third surface. Adopting it is a choice, not a
requirement.

**Error red is muted brick** (`#8C3A2E`), not a system red — a saturated red inside
this palette looks like a browser warning. Paired with `error-50 #F6E7E3` as a
field fill so an invalid field is identifiable by fill *and* border, not color
alone.

**Light mode only.** Dark mode was optional in the brief and skipped: the design
leans on cream-paper warmth that doesn't survive inversion, and a wedding site
that's read once doesn't earn the maintenance. The green ramp is complete enough
to build one later if you want it.

---

## Typography

**Cormorant Garamond 300/400/500i + Karla 400/500/600.**

Cormorant at weight 300 at large sizes gives the display type an engraved,
invitation-like feel that a heavier serif can't — but it goes fragile small, so
the rule is **never below 20px**. Section heads use 400.

Karla is the counterweight: a humanist sans with slightly odd letterforms that
keeps the pairing from tipping into stiff-formal, which the "warm, loving"
direction rules out. 400 body, 500 labels, 600 buttons.

**Both are OFL and must be self-hosted** — the CSP blocks font CDNs. The mocks
link Google Fonts *for preview only*; strip those `<link>` tags on port.
Seven woff2 latin subsets, ~120KB total, from `static/fonts/` behind CloudFront
with `@font-face` + `font-display: swap`. Fallback stacks are declared in every
`font-family` in the mocks (`Georgia, 'Times New Roman', serif` /
`system-ui, -apple-system, sans-serif`) so an unstyled first paint is still
readable.

**Fluid type via `clamp()`** rather than a fixed scale with breakpoints — see
"Responsiveness" below.

**Body copy is 19px, not 16px.** Guests skew older than a typical web audience and
half of them read this outdoors on a phone. 16px is the *minimum*, reserved for UI
and form values.

**16px minimum inside every input.** iOS zooms the viewport on focus for anything
smaller, which is the single most common way a mobile form feels broken.

---

## Space, radius, elevation

**4px base scale**, 1–10. Sections use 96px (mobile) → 128px (desktop) of vertical
padding, blocks 48px. Generous whitespace is most of what separates "editorial"
from "template" here, and it costs nothing.

**4px default radius, restrained throughout.** Heavy rounding reads consumer-app,
not invitation. The one flourish is the **arch** (`radius: 50% 50% 4px 4px`),
reserved for portrait engagement photos — it references a chapel window, and it
only works because nothing else on the page is that shape. One per section, max.

**Shadows are green-tinted** (`rgba(20,37,28,…)`), not grey — a neutral shadow over
a warm background turns visibly cold. Used sparingly: cards prefer a `cream-200`
border, and shadow is for things that genuinely float (the sticky nav, the RSVP
card).

---

## Components

**Buttons: 48px minimum height, 16px text.** Filled `forest-800` for primary,
outlined for secondary, underlined text link for tertiary. Exactly one filled
button per screen region so the primary action is never ambiguous.

**Choice cards instead of radio dots** for attending Y/N and plus-one Y/N. A 22px
tap target on a phone in a canyon parking lot is a mis-tap; the whole card is the
`<label>` with the radio visually hidden. This is also why the yes/no options carry
a second line of copy — the extra text is what makes the target big.

**Selected state is a fill inversion** (dark green card, cream text), not a
checkmark or a border change — it's legible at arm's length and doesn't rely on
color perception alone, since the *fill* changes, not just a hue.

**Form fields: `sage-200` border at rest, `forest-700` + gold focus ring on focus.**
The focus ring is a 3px gold glow rather than the browser default so it survives
on both cream and green surfaces.

**Error presentation is three-layered:** a summary block at the top of the form
listing each problem as an anchor link to its field, plus a red label, plus a
filled + bordered field. The summary exists because a phone form is taller than
the viewport — without it, a user who submits an incomplete form sees no change at
all. `role="alert"` and move focus to it.

---

## Imagery

Engagement photos run through **every** section, not just a gallery — that was the
explicit direction, and it's also what carries the "warm, magical" tone that type
and color alone can't.

**Three treatments only**, so a page never becomes a collage:

- **Full-bleed 16:9** — hero and section breaks. `forest-900` scrim at 35% under
  any text (the hero uses a bottom-weighted gradient, 82% → 28%, so the headline
  has contrast without flattening the photo).
- **Arch portrait 3:4** — one per section, the flourish.
- **Square 1:1** — grids, two-up on phone, four-up on desktop.

All placeholders in the mocks are **striped divs with monospace labels** naming
what goes there — swap for real `<img>` against the S3/CloudFront URLs. Serve AVIF
with WebP fallback, `srcset` at 640/1024/1600/2400, `loading="lazy"` below the
fold, explicit `width`/`height` to prevent layout shift.

---

## Responsiveness

**Fluid, not breakpoint-based.** Type uses `clamp()`, multi-column areas use
`grid-template-columns: repeat(auto-fit, minmax(Npx, 1fr))`, and horizontal groups
are wrapping flex rows with `gap`. The result survives 320px → 2560px with **zero
media queries**, which means the port has no breakpoint table to maintain and no
intermediate width that looks broken. Add media queries only where a layout
genuinely needs to *reorder* rather than reflow.

Mobile-first in substance, not just in width: 48px targets, 16px inputs, single
column at every layout's narrow end, RSVP reachable from the sticky bar at all
times.

---

## What the build should adopt

1. **Lift every value in the style guide into one `:root` token partial** using the
   `--color-*` / `--font-*` / `--space-*` / `--radius-*` / `--shadow-*` names shown.
   The mocks inline literal hex on purpose — so you can see the real value in
   context — but the site should reference variables.
2. **Strip the Google Fonts `<link>` tags** and add self-hosted `@font-face`.
3. **The mocks contain no JS.** Sticky-nav reveal, HTMX swaps on the RSVP form,
   the lightbox, and any countdown are the build's to write. Where a state depends
   on interaction (disabled plus-one name field, "not you?" reset), the mock shows
   the state and a monospace note describing the transition.
4. **`data-screen-label` attributes** on each section are design-tool metadata —
   drop them on port.

---

## Open product questions

Flagged, not invented — these are in the dark band at the bottom of the style
guide too. Each one is a decision the design is currently *assuming*.

1. **Dietary notes vs. `notes`.** `RSVP` has `meal_choice` and a general `notes`
   field. The form's "anything we should know?" maps to `notes` — is that doing
   double duty for allergies, or does dietary want its own field the caterer can
   filter on?
2. **Real meal choices.** `meal_choice` is a free `CharField`. The mock invents
   three (short rib / trout / farrotto). What's the real menu, and is it a fixed
   choice set (→ `choices=`) or genuinely free text?
3. **Household grouping.** `Guest` is one person plus an optional plus-one, so a
   family of four means four codes and four separate visits. Worth adding a party
   or household model before Phase 2 hardens the RSVP flow?
4. **Editing a submitted RSVP.** `RSVP.guest` is a `OneToOneField`, so re-entering
   a used code has no defined behavior today and a second submit would collide.
   The success state is designed as an editable receipt with a "Change our answer"
   button. If it should lock instead, that button becomes a line of text.
5. **Alt text.** `Photo` has `caption` but no `alt_text`. Captions are decorative
   and often blank; alt text isn't. Cheap to add now, annoying later.
6. **Schedule content.** The home page's "shape of the day" section has no model
   behind it — no `Event` model exists. Currently hardcoded copy in the mock.
   Template constant, or a model so times can change without a deploy?

Also worth noting: the mock copy (the story, FAQ answers, dress code, hotel names
and rates, reply-by date) is **placeholder written to the right length and tone** —
it needs your real facts before launch. The venue address in the travel card is a
guess.
