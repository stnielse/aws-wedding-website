# Session 07 — Phase 2 kickoff: Design integration

**Date:** 2026-07-28
**Mode:** Execution — port the mid-build design spin's tokens + fonts +
templates into the Django site. No Phase 2 RSVP flow yet.
**Model:** Opus 4.7

---

## Context

Session 6 (`2026-07-25-session-06-phase1-vite-react-island.md`) closed Phase 1:
the frontend build pipeline lives at `frontend/`, `pnpm build` writes to
`backend/static/frontend/`, and `/rsvp/` mounts the `RsvpForm` island from a
Django template.

Between Session 6 and Session 7 the user ran a parallel design spin, driven by
`.claude/mid-build-design-spin.md`, in a separate Claude session. Its outputs
landed at `.claude/design/` on 2026-07-28:

| File | What it is |
| --- | --- |
| `Style Guide.dc.html` | Tokens (color, type, space, radius, shadow), component specs, imagery rules |
| `Home Page.dc.html` | Full home page mock (hero → story → day → travel → photos teaser → RSVP band → registry + FAQ → footer) |
| `RSVP.dc.html` | `/rsvp` in four states: code lookup, empty form, validation errors, submitted receipt |
| `README.md` | Design reasoning + open product questions |
| `support.js` | Runtime for `.dc.html` files. Not part of the port. |

Session 7 is the **design-integration half** of what Session 6 originally
sketched as a two-half Session 7. The Phase 2 RSVP flow (token-scoped URLs,
submit endpoint, real `RsvpForm.jsx`, tests) is deferred to Session 8 to keep
scope tight.

Still deliberately out of scope this session:
- S3 / `django-storages` (Phase 3)
- Real photo storage — image placeholders stay as striped divs per the design's own imagery rules
- Real `RsvpForm.jsx` logic — the island continues to render its stub
- Token-scoped RSVP URLs, submit endpoint, form tests (Session 8)
- Party model + alt_text + meal choices migrations — **decided this session, migrated in Session 8** (they're not design work)

## Session plan

1. Create this session log (in progress).
2. Read `.claude/design/Style Guide.dc.html` end-to-end; extract every color / type / space / radius / shadow value into `backend/static/css/tokens.css` as `:root` custom properties per the naming shown in the mock.
3. Self-host the fonts. Cormorant Garamond 300/400/500i and Karla 400/500/600 (7 woff2 latin subsets, ~120 KB total). Save under `backend/static/fonts/`. Wire `@font-face` + `font-display: swap` in `backend/static/css/fonts.css`. Strip the Google Fonts `<link>` tags from the mocks on port — CSP will block them.
4. Rewrite `backend/templates/base.html` with the token-driven layout, sticky nav (5 items: Home / RSVP / Travel / Registry / Gallery), fluid `clamp()` type scale, and repeating footer nav.
5. Port the home page mock into `backend/templates/home.html` (extends `base.html`). Add a bare pages view + URL for `/`. Image placeholders stay as striped divs — that's what the design specifies for the port.
6. Port the RSVP-landing mock chrome into `backend/templates/rsvp.html`. Keep `#rsvp-root` + `#rsvp-data`; only the surrounding layout changes. React island stays.
7. Wire URL stubs for `/travel/`, `/registry/`, `/gallery/` so nav clicks don't 404. A shared "coming soon" view is fine — Session 8+ builds the real pages.
8. Smoke test: `runserver` on 8765; user hits `/`, `/rsvp/`, nav clicks. Confirm fonts load, tokens applied, island still mounts.
9. Finalize this log — Session 8 handoff, digressions, files touched.

---

## Decisions locked this session

### Design integration

| Area | Decision |
|---|---|
| Session scope | **Design integration only.** Session 6's outlined "second half" (Phase 2 RSVP flow) becomes Session 8. Reason: keep the diff reviewable and avoid half-finished work; the design port is big enough on its own. |
| Ports | Keep Session 6's: **Django 8765, Vite 5175.** No re-wiring cost, matches recent session logs. |
| Tokens location | `backend/static/css/tokens.css` (single `:root` partial). `fonts.css` next to it. Both loaded from `base.html`. Under `static/` (not an app's `static/`) because they're site-global, and `STATICFILES_DIRS` already covers `BASE_DIR / 'static'` from Session 6. |
| Fonts | Self-host **Cormorant Garamond 300/400/500i + Karla 400/500/600** as woff2 under `backend/static/fonts/`. `@font-face` with `font-display: swap`. Mock's Google Fonts `<link>` tags stripped on port (CSP will block them at Phase 4). Fallback stacks preserved verbatim from the mock. |
| Home page image slots | **Striped-div placeholders** with monospace labels naming what goes there (per the design's own port rule). Real `<img>` swap is a Phase 3 concern once S3 is wired. |
| Nav sticky-reveal | The design says the "appears after hero scroll" behavior is the build's job (mock shows a static bar). **Deferred to Session 8+** — sticky-nav-reveal is JS; not a blocker for verifying the port. This session leaves the nav statically below the hero. |
| Placeholder URLs (`/travel/`, `/registry/`, `/gallery/`) | Stub each with a "coming soon" template so nav is complete without 404s. Phase 2 replaces them with real content-driven pages. |

### Open product questions (from `.claude/design/README.md`) — decided this session

Locked here so Session 8's Phase 2 work has clear direction. Model migrations
themselves happen in Session 8, not here.

| Question | Decision | Reasoning |
|---|---|---|
| Q3 — Household grouping | **Add a `Party` model.** `Guest` moves to `ForeignKey(Party)`. `Party` owns the printed `lookup_code` (one code per household). One RSVP row per `Guest`. | A family of four needing four separate codes and four separate visits is bad UX for the primary "wedding invite" use case; a household code is what people expect. Model change is cheap now while the table is empty. Session 8 does the migration. |
| Q4 — Editable RSVP | **Editable receipt.** Success state shows current answers with a "Change our answer" button that reopens the form. Second submit updates the existing `RSVP` row. | Matches the design mock verbatim; keeps the primary CTA available for guests whose plans change. Template copy in Session 7 uses this language. |
| Q2 — Meal choices | **Fixed set via `choices=`.** Seed with the mock's placeholder trio (short rib / trout / farrotto); swap to the real menu once decided. `meal_choice` stays a `CharField`, just gains `choices=` and validators. | Caterer wants counts; free text makes tallies error-prone. Placeholder → real-menu is a one-line diff. |
| Q5 — Photo alt_text | **Add now.** New `alt_text = CharField(max_length=300, blank=True)` on `Photo`. Migration lands in Session 8 alongside the Party migration. | Cheap on an empty table; adding after uploads means somebody backfilling by hand. `caption` and `alt_text` serve different a11y purposes. |

Questions not decided this session (out of Session 7 scope, but noted so
Session 8+ can pick them up):

- Q1 — Dietary notes vs. `notes`. Leaving as-is; revisit if the real caterer wants a filterable dietary field.
- Q6 — Schedule content. Currently hardcoded copy in the mock; template constant vs. `Event` model is a Session 9+ call.

---

## Progress

- [x] Session log created (this file).
- [x] Style Guide tokens extracted into `backend/static/css/tokens.css` (single `:root` partial: colors, fluid clamp() type scale, 4px space scale, radii, green-tinted shadows, focus ring, container widths, motion).
- [x] Fonts self-hosted under `backend/static/fonts/`; `fonts.css` wired with `@font-face` + `font-display: swap`. **Three** files, not seven — see digression.
- [x] `base.html` rewritten as site chrome: loads tokens/fonts/site CSS, sticky nav with 5 items (Home / Travel / Registry / Photos / RSVP-as-filled-button), forest-800 footer that repeats every link + date + venue, `{% block nav %}` / `{% block content %}` / `{% block footer %}` / `{% block scripts %}`.
- [x] Home page mock ported to `home.html` — hero, on-page anchor nav (overrides `{% block nav %}`), story with arch portrait, dark-green schedule timeline, photo break, travel cards, photos teaser grid, RSVP band, registry + FAQ, footer inherited from base. Image slots are striped-div placeholders per the design's own port rule.
- [x] RSVP landing chrome ported to `rsvp.html`: cream-border page background, intro copy, then a card with the short green hero and the React island stub (`#rsvp-root` / `#rsvp-data`) mounted below. Same island contract as Session 6.
- [x] Pages app URLs wired: `/` → `home`, `/travel/` → `travel`, `/registry/` → `registry`, `/gallery/` → `gallery`. Non-home three share `coming_soon.html` with a page title. `config/urls.py` includes `pages.urls` at root.
- [x] Smoke test: user visually confirmed `/`, `/rsvp/`, and coming-soon pages render with the design system applied and self-hosted fonts loading. Also automated `curl -I` on `/`, `/rsvp/`, `/travel/`, `/registry/`, `/gallery/` (all 200) and on `tokens.css`, `fonts.css`, `site.css`, `Karla-400-600-latin.woff2`, `frontend/assets/main.js` (all 200).
- [x] Session log finalized (this section).

### Digressions worth remembering

**Google Fonts now serves variable-font woff2. The "seven files" number in the design is stale.**
The Style Guide asked for seven latin woff2 subsets (Cormorant 300/400/500/400i + Karla 400/500/600, ~120 KB). Google Fonts' CSS2 API today returns a single variable-font URL that covers the whole normal-weight range of a family. So we ended up with **three files, 84 KB** — one Cormorant variable (weight range 300-500), one Cormorant italic (weight 400), one Karla variable (weight range 400-600). Declared in `fonts.css` with `font-weight: 300 500` / `font-weight: 400 600` ranges. Smaller footprint, same result. Filenames encode the range: `CormorantGaramond-300-500-latin.woff2`, `CormorantGaramond-400i-latin.woff2`, `Karla-400-600-latin.woff2`.

**Fetching gotcha.** Google's CSS API serves woff2 URLs only to modern-browser user-agents. The default `curl` UA gets *nothing* (empty CSS). Fix: pass a Chrome UA (`-A 'Mozilla/5.0 ... Chrome/122...'`). Same UA also has to be sent when downloading the woff2 itself; Google gates on `Referer`-less requests too sometimes but a UA alone was enough.

**Bash `while read` and trailing newlines.** First font-download loop wrote a 7-line manifest with no trailing newline; `while IFS=$'\t' read -r ...` silently dropped the last line, and I ended up missing Karla-600. Root cause is a familiar POSIX-ism (`read` returns non-zero on EOF-without-newline and skips the partial line). If we ever script the EC2 fetch of these fonts, either add `[ -n "$line" ] &&` inside the loop or terminate the input properly.

**CSS architecture chose "small utility set + component classes".** Three CSS files under `backend/static/css/`: `tokens.css` (variables only), `fonts.css` (`@font-face` only), `site.css` (everything else — reset, layout primitives, buttons, nav, footer, hero, all home-page section styles, RSVP-page chrome). No CSS framework; templates use classes instead of inline styles. `site.css` is ~600 lines but flat and reads top-to-bottom by page/section — easy to grep. Considered splitting into `layout.css` + `home.css` + `rsvp.css` but the total is small and one file loads with one request; revisit if it grows past ~1500 lines.

**Sticky nav on the home page has two variants.** `base.html` renders a default site-level `{% block nav %}` — used on `/rsvp/`, `/travel/`, `/registry/`, `/gallery/`. `home.html` overrides `{% block nav %}` to empty (so nothing sits above the hero) and then renders its own in-content `.top-nav` **below** the hero with anchor links (`#story`, `#day`, `#travel`, `#photos`, `#registry`, `#faq`). This matches the mock exactly ("in the mock the bar simply sits below the hero"). The "appears after hero scroll" behavior stays deferred — same `.top-nav` element, and once we add ~20 lines of vanilla JS in Session 8 (IntersectionObserver on the hero) it just works.

**`STATICFILES_DIRS` from Session 6 already covers this.** `backend/static/{css,fonts}/` were picked up by `runserver`'s static finder without any settings change — Session 6 added `STATICFILES_DIRS = [BASE_DIR / 'static']` when Vite's build output was outside an app dir, and that setting covers the new dirs too.

**`{% url 'pages:travel' %}` etc. required creating `pages/urls.py` from scratch.** The pages app existed after Session 5 but had no URL config yet — routing `/` was still open. Wired it here rather than deferring, because `base.html`'s nav needs every URL name to resolve or every template render blows up.

**Coming-soon template pattern.** Rather than three near-identical templates for `/travel/`, `/registry/`, `/gallery/`, one `coming_soon.html` takes a `page_title` context var. Cheap DRY; when Session 8 builds `/travel/` for real, that view swaps to `travel.html` and `coming_soon.html` stays around for the remaining two.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-07-28-session-07-design-integration.md` — this log
- `backend/static/css/tokens.css` — design tokens (colors, type, space, radii, shadows, focus ring, container, motion)
- `backend/static/css/fonts.css` — self-hosted `@font-face` declarations for Cormorant Garamond + Karla, weight-range variable fonts
- `backend/static/css/site.css` — site-wide styles (reset, layout, buttons, top nav, footer, hero, story, day/timeline, travel, photos-teaser, RSVP band, registry+FAQ, RSVP page chrome, image placeholders)
- `backend/static/fonts/CormorantGaramond-300-500-latin.woff2` — variable font (300-500 normal)
- `backend/static/fonts/CormorantGaramond-400i-latin.woff2` — italic weight 400
- `backend/static/fonts/Karla-400-600-latin.woff2` — variable font (400-600 normal)
- `backend/templates/home.html` — home page (hero, on-page nav, story, day, photo break, travel, photos teaser, RSVP band, registry+FAQ)
- `backend/templates/coming_soon.html` — placeholder for `/travel/`, `/registry/`, `/gallery/`
- `backend/pages/urls.py` — `app_name = 'pages'`; routes for `home`, `travel`, `registry`, `gallery`

**Modified:**
- `backend/templates/base.html` — full site chrome; loads tokens/fonts/site CSS; renders sticky top nav + footer as blocks; `{% block content %}` between them
- `backend/templates/rsvp.html` — landing chrome ported from RSVP.dc.html state 1; keeps `#rsvp-root` + `#rsvp-data`; React island contract unchanged
- `backend/pages/views.py` — `home`, `travel`, `registry`, `gallery` views (last three share `coming_soon.html`)
- `backend/config/urls.py` — includes `pages.urls` at `''`

**Not tracked by git (background scratch):**
- `/tmp/gfonts.css` — the Google Fonts CSS2 response used to extract woff2 URLs
- `/tmp/font_manifest.txt` — intermediate filename→URL mapping

Per working contract, all `git add` / `git commit` is left to the user.

## Session 8 handoff

Session 8 is Phase 2 as originally scoped, plus the model migrations
Session 7 decided but did not implement. Rough order:

1. **Model migrations.** Add `Party` (name, lookup_code, plus_one_allowed?, notes?); change `Guest.lookup_code` → `Guest.party = ForeignKey(Party)`. Add `Photo.alt_text`. Change `RSVP.meal_choice` to `CharField(max_length=100, choices=MEAL_CHOICES)` — start with placeholder choices. Register everything in admin.
2. **URL scheme.** `/rsvp/` becomes `/rsvp/<code>/` where `<code>` matches `Party.lookup_code`. View loads the party, lists its guests, passes props into `rsvp.html`. Plain `/rsvp/` stays as the code-lookup landing (design's first state).
3. **Submit endpoint.** `rsvp/urls.py` — `path('<code>/submit/', views.submit, name='submit')`. Accepts POST with CSRF; creates/updates one `RSVP` per guest in the party. Returns JSON.
4. **`RsvpForm.jsx` for real.** Code lookup → form → success (editable receipt) states from `RSVP.dc.html`. Post to `props.submitUrl` with `X-CSRFToken: props.csrfToken`. Error summary at top with `role="alert"` per the design.
5. **Tests.** GET `/rsvp/<valid-code>/` (200, `rsvp-root` present); POST `submit` with valid/invalid payloads.
6. **Sticky-nav-reveal JS** (small, hand-written; no framework). Nav appears once the hero scrolls out of view.

Before touching anything in Session 8:

- Read this file, then Sessions 5 + 6.
- Re-read the handoff's Phase 2 section and the `.claude/design/` README + Style Guide.
- Use `.venv/bin/python` for Django, `pnpm` (pinned via corepack) for frontend.
- Vite 8 dev server is `http://localhost:5175/`, not `127.0.0.1` — Session 6 quirk still applies.
- Every new dep — Python or JS — gets exact-pinned. Strip the `^` from `package.json` after any `pnpm add`.

## Open questions / follow-ups

- **Sticky-nav reveal** — deferred; small hand-rolled JS in Session 8.
- **Real engagement photos** — swap placeholder divs for `<img>` once S3 is wired (Phase 3). Alt text goes with them.
- **Q1 dietary + Q6 schedule** — see decisions table; still open.
- **`django-vite`** — still deferred; Session 6's follow-up applies.
- **Cache-busting the built bundle** — Phase 3 concern.
- **`__str__` methods on models** — still open from Session 5. Model changes in Session 8 are a good moment to add them across the board.
- **Handoff `apt`/`ubuntu` cleanup** — Phase 4.
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3.
