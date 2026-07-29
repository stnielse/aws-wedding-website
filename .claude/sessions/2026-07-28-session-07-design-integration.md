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
- [ ] Style Guide tokens extracted into `tokens.css`.
- [ ] Fonts self-hosted under `backend/static/fonts/`; `fonts.css` wired.
- [ ] `base.html` rewritten with tokens + nav + footer.
- [ ] Home page mock ported to `home.html`; pages view + `/` URL added.
- [ ] RSVP landing chrome ported to `rsvp.html`.
- [ ] URL stubs for `/travel/`, `/registry/`, `/gallery/`.
- [ ] Smoke test: `/` renders with design system; `/rsvp/` island mounts under new chrome; nav links resolve.
- [ ] Session log finalized (this section).

### Digressions worth remembering

_(Filled in as they come up.)_

## Files created / modified this session

_(Filled in at wrap.)_

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
