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
- [ ] Model migrations for `rsvp` + `gallery` written and applied.
- [ ] Admin registrations updated; `__str__` methods added.
- [ ] `rsvp/urls.py` reshaped to landing / party / submit.
- [ ] `rsvp/views.py` implements landing, party, submit.
- [ ] `rsvp_landing.html` and `rsvp_party.html` templates in place; old `rsvp.html` removed.
- [ ] `RsvpForm.jsx` real implementation replacing the stub.
- [ ] `nav-reveal.js` written and loaded on home only.
- [ ] Tests in `backend/rsvp/tests.py` — landing, party 404 / 200, submit valid / invalid.
- [ ] End-to-end smoke test with a real Party in admin.
- [ ] Session log finalized.

### Digressions worth remembering

_(filled during work)_

## Files created / modified this session

_(filled during work)_

## Session 9 handoff

_(filled at end of session)_

## Open questions / follow-ups

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Real engagement photos + alt_text values** — Phase 3 when S3 is wired.
- **`django-vite`** — still deferred; revisit if HMR-during-Django-dev becomes valuable.
- **Cache-busting the built bundle** — Phase 3 concern.
- **Handoff `apt`/`ubuntu` cleanup** — Phase 4.
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3.
