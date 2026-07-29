# Session 08 — Phase 2 RSVP flow + model migrations

**Date:** 2026-07-29
**Mode:** Execution — Phase 2 as originally scoped, plus the model migrations
Session 7 decided but did not implement.
**Model:** Opus 4.7

---

## Context

Session 7 (`2026-07-28-session-07-design-integration.md`) ported the design spin's
tokens, self-hosted fonts, and full home + RSVP-landing chrome into Django
templates. That closes the "design integration" half of what was originally
sketched as a two-half Session 7 in Session 6's handoff.

Session 8 is the second half of that plan plus the model migrations Session 7
locked but deferred. When this session lands, the site will have:

- A real household-oriented RSVP data model (`Party` owning the printed code, one
  RSVP row per Guest, meal choices constrained, Photo alt-text)
- A working `/rsvp/` → `/rsvp/<code>/` → `submit` flow driven by a real
  `RsvpForm.jsx` (not the stub)
- Server-side validation with the design's error summary at the top
- An editable receipt (re-entering a used code shows the current answers)
- A small hand-written sticky-nav reveal script (deferred from Session 7)
- Tests covering the two main URLs and the submit endpoint's happy + sad paths

Still out of scope this session (deferred to Session 9+):
- Real gallery / photo storage on S3 (Phase 3)
- HTMX for anything else — the RSVP flow uses React only
- `django-vite` (still deferred; Session 7 follow-up)
- ManifestStaticFilesStorage / cache-busting (Phase 3)
- Real travel / registry / gallery / FAQ page interiors (still coming-soon)
- Transactional emails (out of Phase 2 scope entirely; deferred)

## Session plan

1. Create this session log (in progress).
2. **Model migrations** (single migration per app touched):
   - `rsvp`: add `Party` model (name, lookup_code unique, notes); change `Guest` — drop `lookup_code`, add `party = ForeignKey(Party, on_delete=CASCADE, related_name='guests')`; add `MEAL_CHOICES` module constant and `choices=MEAL_CHOICES` on `RSVP.meal_choice` and `RSVP.plus_one_meal`.
   - `gallery`: add `Photo.alt_text = CharField(max_length=300, blank=True)`.
   - Add `__str__` methods to all models (Session 5 follow-up).
   - Register `Party` in admin with `list_display = ('name', 'lookup_code')`; keep Guest / RSVP / Photo registrations working (they already exist as plain `admin.site.register`; expand once we touch them).
   - `makemigrations` then `migrate` (SQLite, dev; empty tables so no data-migration needed).
3. **URL scheme.** `rsvp/urls.py`:
   - `path('', views.landing, name='landing')` — code lookup (state 1). GET renders form; POST validates code and redirects to party URL (or re-renders with error).
   - `path('<str:code>/', views.party, name='party')` — resolves lookup_code case-insensitively, renders `rsvp_party.html` with `party` + `guests` + existing `rsvps` serialized into the island's `#rsvp-data`.
   - `path('<str:code>/submit/', views.submit, name='submit')` — POST-only JSON endpoint. Creates or updates one RSVP row per guest in the party. Returns `{ok: true, receipt: {...}}` on success or `{ok: false, errors: [...]}` on validation failure.
4. **Templates.**
   - Rename current `rsvp.html` → `rsvp_landing.html`; adapt to state 1 (code lookup form, POSTs to `landing` view). Plain Django form, no island.
   - New `rsvp_party.html` — hosts the React island with `#rsvp-data` containing party JSON + `submitUrl` + `csrfToken`. Extends `base.html`.
5. **Real `RsvpForm.jsx`.** For each guest in `party.guests`, render:
   - Header ("Hello, {guest.name}") and reply-by note
   - Attending Yes / No choice cards (fill inversion selected state)
   - Meal `<select>` bound to `MEAL_CHOICES` (only when attending)
   - Plus-one card group (only when `guest.plus_one_allowed`): Yes / Coming alone; name + meal fields disabled until Yes
   - Notes textarea (per guest)
   Submit posts `[{ guest_id, attending, meal_choice, plus_one_attending, plus_one_name, plus_one_meal, notes }, ...]` to `props.submitUrl` with `X-CSRFToken: props.csrfToken`. On 200 with `receipt`, render state 4. On 400 with `errors`, render state 3 (summary at top, per-field red state).
6. **Sticky-nav reveal.** New `backend/static/js/nav-reveal.js`. IntersectionObserver on `.hero` — when it stops intersecting the viewport, toggle `body.is-nav-revealed`. Loaded from `home.html` only (the other pages don't have a hero the nav needs to appear over). ~20 lines.
7. Smoke test in browser: user creates a Party in admin with two Guests, hits `/rsvp/`, enters the code, submits, sees receipt.
8. **Tests (penultimate step per working contract).** `backend/rsvp/tests.py`:
   - `GET /rsvp/` returns 200 and contains the lookup form
   - `GET /rsvp/<invalid>/` returns 404
   - `GET /rsvp/<valid>/` returns 200 and contains `id="rsvp-root"`
   - `POST /rsvp/<valid>/submit/` with a valid payload creates/updates RSVPs and returns `{ok: true}`
   - `POST /rsvp/<valid>/submit/` with an invalid payload returns 400 + `{ok: false, errors: [...]}`
   - Use `Client(SERVER_NAME='127.0.0.1')` per the Session 5 digression
9. Finalize this log.

---

## Decisions locked this session

### Model shape

| Area | Decision |
|---|---|
| `Party.name` | Admin-facing display label (e.g., "The Alvarez–Okafor party"). Not shown on the form — the form addresses each Guest by their own name. |
| `Party.lookup_code` | Six-character `CharField(max_length=20, unique=True)` — kept generous room for prefixes like `FALLS-3K7` from the mock. Stored uppercase; lookup is case-insensitive via `.filter(lookup_code__iexact=…)`. |
| `Party.notes` | Optional `TextField(blank=True)` for private admin notes (allergies noted by phone, etc.). Not exposed on the form. |
| `plus_one_allowed` | **Stays on `Guest`**, not on `Party`. Each guest independently gets a plus-one flag (Marguerite's dad might not). Cheaper than modeling +1 slots at party level and matches the mock's per-guest UI. |
| `MEAL_CHOICES` | Module-level constant in `rsvp/models.py`: `[('short_rib', 'Braised short rib'), ('trout', 'Trout, almondine'), ('farrotto', 'Wild mushroom farrotto')]`. Placeholders from the design mock — the caterer confirms the real menu closer to the wedding; swap-in is a one-line diff. Applied to both `RSVP.meal_choice` and `RSVP.plus_one_meal`. |
| `Photo.alt_text` | `CharField(max_length=300, blank=True)`. Blank-allowed because captions may double as alt for decorative photos; the field exists so a11y-critical images can override. |
| `__str__` methods | Added across all six models (Session 5 follow-up) — Party by name, Guest by name, RSVP by "RSVP: {guest.name}", Photo by caption or filename, FAQ by question, RegistryLink by name, HotelBlock by hotel name. Not required for correctness but the admin changelists become readable. |

### URL & flow

| Area | Decision |
|---|---|
| Landing (state 1) is a plain HTML POST form, not a React island. | The lookup step needs one input and a submit — dropping React on it means the page renders and submits without waiting on the bundle. React only mounts once we're on `/rsvp/<code>/` where the multi-guest form warrants it. |
| Code normalization | Store `Party.lookup_code` upper-cased in `save()`; the landing view normalizes input with `.upper().strip()` before redirect. Case-insensitive lookup is the safety net for direct URL entry. |
| Submit endpoint | JSON POST returning JSON. Not `HttpResponseRedirect`, not HTML — the React form owns the transition to state 4. Same URL for create and update: `RSVP.objects.update_or_create(guest=…, defaults=…)` per guest. |
| Receipt on re-entry | Design says "State 4 is also the view on re-entering a used code." Implementation: `party` view checks if every guest has an RSVP; if so, serialize into `existingRsvps` prop and the React form opens in receipt mode. "Change our answer" flips it back into form mode client-side; second submit updates the rows. |
| Sticky-nav-reveal scope | Home page only. Every other page has the site's default `{% block nav %}` already visible above the fold — no hero to hide behind. Loaded via `{% block scripts %}` override in `home.html`, not `base.html`. |

### Out-of-scope defer log

- **Q1 — dietary vs. notes.** Still not decided; leaving as-is. Revisit if the caterer wants a filterable dietary field.
- **Q6 — schedule content.** Still hardcoded in `home.html`; template constant vs. `Event` model is Session 9+ material.
- **`django-vite`.** Not adopted; the hardcoded `<script src="{% static … %}">` continues to work for prod, and the parallel `pnpm dev` server is fine for React iteration.
- **Cache-busting on `main.js`.** `entryFileNames: 'assets/main.js'` still unhashed — Phase 3 will decide between ManifestStaticFilesStorage and Vite hashing + manifest read.
- **Transactional emails / reminder emails.** Never in Phase 2 scope — the couple can DM anyone missing.

---

## Progress

- [x] Session log created (this file).
- [x] Model migrations for `rsvp` + `gallery` written and applied (hand-written `0002` for rsvp because Django would have prompted for an FK default; `0002_photo_alt_text` for gallery is auto-generated).
- [x] Admin registrations upgraded with `list_display` / `search_fields` / `autocomplete_fields`; `__str__` methods added on all six models.
- [x] `rsvp/urls.py` reshaped to landing / party / submit (`app_name = 'rsvp'`, names `landing`, `party`, `submit`). All six templates that referenced the old `rsvp:index` renamed to `rsvp:landing`.
- [x] `rsvp/views.py` implements landing (GET+POST), party (`@ensure_csrf_cookie`, `get_token`), submit (POST JSON in, JSON out). Server validates: attending Y/N, meal in `MEAL_CHOICES`, plus-one name + meal required when plus_one_attending, guest_id must belong to this party.
- [x] `rsvp_landing.html` and `rsvp_party.html` templates in place; old `rsvp.html` removed. Landing is a plain HTML `<form>`; party page hosts the `#rsvp-data` JSON + `#rsvp-root` island.
- [x] `RsvpForm.jsx` real implementation replacing the stub — code lookup handoff, per-guest form sections, error summary with focus-move, plus-one card group with disabled name/meal fields, editable receipt.
- [x] `nav-reveal.js` written and loaded on home only via `home.html`'s `{% block scripts %}`. IntersectionObserver toggles `.top-nav.is-revealed` for the entrance shadow.
- [x] End-to-end smoke test — user click-through of `/`, `/rsvp/`, `/rsvp/FALLS-3K7/`, form → receipt → change-answer → back to form. Nav-reveal on scroll verified. curl matrix: `/`, `/rsvp/`, `/rsvp/FALLS-3K7/`, `/rsvp/falls-3k7/`, `/rsvp/CANYON-9M/`, `/travel/`, `/registry/`, `/gallery/`, `/static/frontend/assets/main.js`, `/static/js/nav-reveal.js`, `/static/css/site.css` all 200; `/rsvp/NOPE-XYZ/` 404.
- [x] Tests in `backend/rsvp/tests.py` — 21 tests across 4 classes (LandingTests, PartyPageTests, SubmitTests, ModelTests). All passing. `SubmitTests` uses `Client(enforce_csrf_checks=True)` and warms up the csrftoken cookie via a GET against the party page.
- [x] Session log finalized (this section).

### Digressions worth remembering

**`makemigrations --noinput` bails on a non-null FK swap.** Adding `Guest.party = ForeignKey(...)` without `null=True` while simultaneously removing `Guest.lookup_code` made Django refuse to auto-generate the migration in non-interactive mode. Reason: Django needs a default value to populate existing rows, and `--noinput` can't prompt. The Guest table was empty in our dev DB, so the "default" was never actually going to be applied — but Django's check runs regardless. Fix: hand-write the migration with `preserve_default=False` and a sentinel `default=1`. Documented in the migration file so we can port this cleanly when the Postgres prod DB gets built.

**`csrfToken` in the JSON payload is not optional.** First submit test 403'd with "CSRF cookie not set" — the party template had no `{% csrf_token %}` template tag, so Django never set the `csrftoken` cookie on the GET, and the React fetch had nothing to send. Two fixes in one: `@ensure_csrf_cookie` on the `party` view forces the cookie set, and `get_token(request)` puts the value into the JSON payload so the fetch's `X-CSRFToken` header matches. Learn once, apply everywhere React-in-Django posts back.

**Session 5's `Client(SERVER_NAME='127.0.0.1')` workaround doesn't apply inside `TestCase`.** Django's `TestCase` auto-adds `testserver` to `ALLOWED_HOSTS` for the run — plain `Client()` works. The 127.0.0.1 workaround was only needed for `manage.py shell` `Client` usage.

**CSRF-enforced test setup pattern.** `Client(enforce_csrf_checks=True)` is off by default in tests. Turned it on in `SubmitTests` and warm up the cookie exactly the way the browser would — an initial GET against the party page whose response sets `csrftoken`, then a POST that echoes the same value via `HTTP_X_CSRFTOKEN`. Now the test suite covers the CSRF path end-to-end instead of bypassing it.

**HTML entity escaping bit the first assertion.** `assertContains(response, "can't find that code")` failed because Django escaped the apostrophe to `&#x27;`. Switch the assertion to a substring without punctuation (`Double-check the invitation`). General rule: `assertContains` compares against the raw HTML; assert on unpunctuated substrings, or use `html=True` and match a fragment.

**Sticky nav "reveal" was mostly CSS already.** Session 7 deferred this expecting non-trivial JS, but `.top-nav` was already `position: sticky; top: 0`, so it appears naturally as the hero scrolls up. The "reveal" polish is a single class toggled by an IntersectionObserver — 8 real lines of JS — and only controls whether the nav gets an entrance shadow. Cheap.

**Nav-reveal has a first-paint flicker on refresh mid-page.** If you refresh with the nav already stuck at top, `.is-revealed` isn't set until the IntersectionObserver fires (after `defer`red script executes). The shadow snaps in ~50-100ms later. Not worth SSR'ing a class for; noting so we don't chase it.

**Meal choices carry both value and label in the receipt payload.** The React receipt renders "Trout, almondine" not "trout", so the view helper (`_rsvp_to_dict`) resolves each stored value against `dict(MEAL_CHOICES)` and includes `meal_choice_label` + `plus_one_meal_label`. Keeps the client dumb — it just displays what the server returned.

**Party model has `verbose_name_plural = 'parties'`.** Django's default pluralizer would have said "Partys" in the admin. One-liner Meta override.

**Test-seed script left an artifact.** The user's click-through created RSVPs on `FALLS-3K7`; between demos, wipe via `RSVP.objects.filter(guest__party__lookup_code='FALLS-3K7').delete()` (or use the code above). Session 9 could add a `manage.py reset_test_parties` management command if this becomes routine.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-07-29-session-08-phase2-rsvp-flow.md` — this log
- `backend/rsvp/migrations/0002_party_meal_choices_and_guest_fk.py` — hand-written; creates Party, swaps Guest.lookup_code → Guest.party FK, adds meal `choices=` on RSVP
- `backend/gallery/migrations/0002_photo_alt_text.py` — auto-generated; adds Photo.alt_text
- `backend/templates/rsvp_landing.html` — state 1 code lookup (plain Django form)
- `backend/templates/rsvp_party.html` — state 2/3/4 host for the React island
- `backend/static/js/nav-reveal.js` — IntersectionObserver toggling `.top-nav.is-revealed`
- `backend/rsvp/tests.py` — 21 tests, 4 classes (was empty scaffold)

**Modified:**
- `CLAUDE.md` — added "Tests before finalization" rule; added "Local paths (pinned)" section with venv Python + runserver port + Vite quirk
- `backend/rsvp/models.py` — MEAL_CHOICES module constant; Party model with lookup_code save-normalization; Guest gains `party` FK, drops `lookup_code`; RSVP.meal_choice + plus_one_meal gain `choices=`; `__str__` on all three
- `backend/rsvp/admin.py` — ModelAdmin subclasses with list_display / search_fields / autocomplete_fields; Party registered
- `backend/rsvp/urls.py` — landing / party / submit routes; old `index` name retired
- `backend/rsvp/views.py` — full rewrite: landing (GET+POST), party (`@ensure_csrf_cookie`, JSON serialize), submit (POST JSON with per-field validation, update_or_create per guest)
- `backend/gallery/models.py` — added Photo.alt_text; added `__str__`
- `backend/gallery/admin.py` — ModelAdmin with list_display / search_fields
- `backend/pages/models.py` — added `__str__` on FAQ, RegistryLink, HotelBlock
- `backend/static/css/site.css` — added form primitives (label, input, select, textarea, btn, error summary), rsvp-lookup (state 1), rsvp-form (state 2/3), rsvp-receipt (state 4), choice-cards, plus-one-block; added `.top-nav.is-revealed` shadow hook
- `backend/templates/base.html` — renamed `rsvp:index` → `rsvp:landing`
- `backend/templates/home.html` — renamed `rsvp:index` → `rsvp:landing`; added `{% load static %}` and `{% block scripts %}` loading `nav-reveal.js`
- `backend/templates/coming_soon.html` — renamed `rsvp:index` → `rsvp:landing`
- `frontend/src/RsvpForm.jsx` — real implementation (was a JSON-dump stub): per-guest sections, choice cards, error summary with focus-move, plus-one block, editable receipt

**Deleted:**
- `backend/templates/rsvp.html` — split into `rsvp_landing.html` + `rsvp_party.html`

**Also touched (not tracked by git):**
- `backend/db.sqlite3` — two new migrations applied; two seed Parties (`FALLS-3K7`, `CANYON-9M`) with 6 total Guests for the smoke test
- `backend/static/frontend/assets/main.js` — Vite build output, 199.86 KB (gzip 62.73 KB), same path as Session 7
- Ephemeral: two runserver processes started + killed during smoke test; `/tmp/rsvp-cookies.txt` for the curl smoke test

Per working contract, all `git add` / `git commit` is left to the user.

## Session 9 handoff

Session 9 is the first Phase 3 session — cloud storage for gallery photos. Prep list:

1. **Wire `django-storages` for S3.** Pin exact version in `backend/requirements/base.txt`. Configure `STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage', ...}` in `production.py` only; `local.py` keeps local-media behavior. Bucket name + IAM policy live in the existing Terraform.
2. **CloudFront OAC in front of the bucket.** OAC (Origin Access Control), not the deprecated OAI. Signed private-bucket → public-URL flow. Cache-Control on Photo uploads = 1 year, immutable.
3. **Real photo uploads.** Django admin's default `ImageField` upload widget → `django-storages` → S3. Verify pillow can read the uploaded file back via `Photo.image.url` (should be a CloudFront URL in prod).
4. **Swap the home page's striped-div placeholders for real `<img>`.** Hero, arch portrait, photo break, photos teaser. `srcset` at 640/1024/1600/2400, `loading="lazy"` below the fold, explicit `width`/`height`.
5. **Cache-busting for `main.js`.** Decide: `ManifestStaticFilesStorage` (Django-side hashing) or re-enable Vite hashing + Vite's `manifest.json` read via templatetag. Pick and pin.
6. **Model `__str__` follow-ups?** All models now have them. Remaining polish: `list_display` on FAQ / RegistryLink / HotelBlock (currently plain `admin.site.register`).

Also potentially worth folding in:
- **`cost-guard` and `wedding-copy-editor` subagents** (from the handoff, still deferred).
- **Cost check.** After S3+CloudFront lands, verify AWS bill projection is still <$5/month for the July–May 2027 lifetime. Handoff's cost estimate assumes minimal traffic.

Before touching anything in Session 9:

- Read this file (Session 8), plus Session 7's design integration notes for token/CSS names.
- Re-read handoff's Phase 3 section + the CloudFront amendment.
- **Python:** `/Users/stevennielsen/aws-wedding-website/.venv/bin/python` (now pinned in CLAUDE.md).
- **Frontend:** `pnpm` via corepack from `frontend/`.
- **Runserver:** 8765. **Vite dev:** `http://localhost:5175/`, not `127.0.0.1` (Vite 8 quirk).
- Every direct dep gets exact-pinned per [[feedback-strict-version-pins]].
- Tests are the penultimate step per the working contract addition this session.

## Open questions / follow-ups

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Real engagement photos + alt_text values** — Phase 3 when S3 is wired.
- **`django-vite`** — still deferred; revisit if HMR-during-Django-dev becomes valuable.
- **Cache-busting the built bundle** — Phase 3 concern.
- **Handoff `apt`/`ubuntu` cleanup** — Phase 4.
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3.
