# Session 05 — Phase 1 Apps and Models

**Date:** 2026-07-24
**Mode:** Execution — the three apps and their models on top of the Session 4 skeleton
**Model:** Opus 4.7

---

## Context

Session 4 (`2026-07-17-session-04-phase1-django-skeleton.md`) landed the Django
skeleton: `.venv/` with Python 3.12 and Django 5.2.16, `backend/config/` with
the settings split (`base.py`/`local.py`/`production.py`), `manage.py` and
`wsgi.py` wired to the right defaults, requirements exact-pinned, SQLite
migrated with the 18 built-in migrations, and `runserver` serving the Django
welcome page + admin login page. **No apps yet.** The DB has no users.

Session 5 is the middle slice of Phase 1 per the amended plan
(`.claude/wedding-site-handoff.md` → "Amendments" → "Phase 1 split across
sessions"): create the three apps, wire up the models exactly as the handoff
spec dictates, register each model in the admin, migrate, create a superuser,
and verify the admin UI can create rows for every model.

Session 6 will do Vite + React + one mounted island; S3 wiring is
deliberately deferred (Photo's `ImageField` stays on local `MEDIA_ROOT` for
now — `MEDIA_ROOT`/`MEDIA_URL` were already set in `local.py` during
Session 4).

## Session plan

1. Create three apps from `backend/` inside the venv:
   `python manage.py startapp rsvp`, then `gallery`, then `pages`.
2. Add all three to `INSTALLED_APPS` in `config/settings/base.py`.
3. Write the models exactly as in the handoff
   (`.claude/wedding-site-handoff.md:117-167`):
   - `rsvp/models.py` — `Guest`, `RSVP`
   - `gallery/models.py` — `Photo`
   - `pages/models.py` — `FAQ`, `RegistryLink`, `HotelBlock`
4. Register every model in each app's `admin.py` with plain
   `admin.site.register(...)`.
5. `python manage.py makemigrations` then `migrate` — still SQLite via
   `config.settings.local`.
6. `python manage.py createsuperuser` — the Session-4 DB has no users.
7. `runserver`, log in at `/admin/`, confirm every model shows up and a row
   can be created via the admin UI.

Explicitly out of scope this session: `django-storages`/S3, Vite, React,
HTMX, templates. Photo's `ImageField` on local `MEDIA_ROOT` is fine at this
stage.

---

## Decisions locked this session

| Area | Decision |
|---|---|
| App names & layout | `rsvp`, `gallery`, `pages` — flat under `backend/`, matching the handoff exactly. `pages` is intentionally generic to group the three near-static content models (FAQ, RegistryLink, HotelBlock) that don't each merit their own app. Nested `backend/apps/…` layout rejected as premature for a 3-app project. |
| Model fidelity | Models written verbatim from handoff lines 117-167 — no `__str__`, no `verbose_name`, no extra `Meta` beyond what the handoff specifies. Admin readability is a fine follow-up but not this session's scope. |
| Pillow location | `Pillow==12.3.0` lives in `backend/requirements/base.txt`, not `local.txt`. Reason: `gallery.Photo.image = ImageField(...)` fails Django's system check without Pillow regardless of storage backend, so both local and production need it. Exact-pinned per [[feedback-strict-version-pins]]. |
| Admin registration style | Plain `admin.site.register(Model)` for all six models. No `ModelAdmin` subclasses yet. Custom list displays / filters / search will land in a later session once we have real usage patterns to design around. |
| Admin verification method | Combination of (a) programmatic model-registry inspection, (b) ORM round-trip creating one row per model incl. cascade-delete check, (c) authenticated Django test-client GET of all 13 admin URLs, and (d) manual browser click-through by the user. This is stronger than any one of those alone. |

---

## Progress

- ✅ Session log created (this file).
- ✅ Three apps scaffolded via `python manage.py startapp` — `rsvp`, `gallery`, `pages` — all flat under `backend/`.
- ✅ Apps added to `INSTALLED_APPS` in `config/settings/base.py`.
- ✅ Models written per handoff — Guest, RSVP (rsvp); Photo (gallery); FAQ, RegistryLink, HotelBlock (pages).
- ✅ All six models registered in each app's `admin.py`.
- ✅ `Pillow==12.3.0` added to `backend/requirements/base.txt` (needed by `ImageField`).
- ✅ `python manage.py check` — 0 issues after Pillow install.
- ✅ `makemigrations` produced three initial migrations (one per app); `migrate` applied clean on SQLite.
- ✅ Superuser created (user ran `createsuperuser` themselves; creds never left their machine).
- ✅ Admin end-to-end verified — model registry, ORM round-trip (create → cascade delete → cleanup), authenticated GET of `/admin/` + every `<app>/<model>/` and `<app>/<model>/add/` URL (all 200), plus manual browser click-through by user.

### Digressions worth remembering

**Pillow was a required dep, not a bonus.** `Photo.image = ImageField(...)`
triggers `fields.E210` at `manage.py check` time without Pillow installed —
so it's genuinely non-optional for anyone cloning the repo. That's why it
sits in `base.txt` rather than an env-specific requirements file.

**Django test client → `DisallowedHost`.** `Client()` defaults to hostname
`testserver`, which isn't in `ALLOWED_HOSTS` even with `DEBUG=True` (Django's
DEBUG shortcut only auto-allows `localhost`/`127.0.0.1`/`[::1]`, not
`testserver`). Django's `TestCase` framework normally adds `testserver` to
`ALLOWED_HOSTS` automatically for the duration of the test run, but that
override does not fire when you instantiate `Client` from `manage.py shell`.
Workaround used here: `Client(SERVER_NAME='127.0.0.1')`. Worth remembering
before writing any future `manage.py shell` scripts that exercise views.

**`MEDIA_ROOT` was already wired.** Session 4's `local.py` sets
`MEDIA_ROOT = BASE_DIR / 'media'` and `MEDIA_URL = '/media/'`. The Session 4
log doesn't call this out explicitly, but that's why Photo's smoke-test upload
landed under `backend/media/gallery/`. `backend/media/` is already gitignored.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-07-24-session-05-phase1-apps-and-models.md` — this log
- `backend/rsvp/` — `startapp` scaffold (apps.py, admin.py, models.py, tests.py, views.py, migrations/, __init__.py)
- `backend/gallery/` — same scaffold
- `backend/pages/` — same scaffold
- `backend/rsvp/migrations/0001_initial.py` — Guest, RSVP
- `backend/gallery/migrations/0001_initial.py` — Photo
- `backend/pages/migrations/0001_initial.py` — FAQ, HotelBlock, RegistryLink

**Modified:**
- `backend/config/settings/base.py` — added `rsvp`, `gallery`, `pages` to `INSTALLED_APPS`
- `backend/rsvp/models.py` — Guest + RSVP per handoff
- `backend/rsvp/admin.py` — register both
- `backend/gallery/models.py` — Photo per handoff
- `backend/gallery/admin.py` — register Photo
- `backend/pages/models.py` — FAQ, RegistryLink, HotelBlock per handoff
- `backend/pages/admin.py` — register all three
- `backend/requirements/base.txt` — added `Pillow==12.3.0` (with a comment explaining why it lives here, not in an env file)

**Also touched (not tracked by git):**
- `backend/db.sqlite3` — gained the six new tables + a superuser row (file is gitignored)
- Ephemeral: created and cleaned up `backend/media/gallery/smoke.png` during the ORM smoke test; the `backend/media/` directory was removed after cleanup

Per working contract, all `git add` / `git commit` is left to the user.

## Session 6 handoff

**Goal:** Vite + React scaffold + one mounted island — the last slice of
Phase 1. This closes out Phase 1 and unblocks Phase 2 (core features).

**Before touching anything:**

- Read this file (Session 5 log) and Session 4's log — the venv convention,
  the settings module split, and the app layout are established there.
- Every Python invocation runs against
  `/Users/stevennielsen/aws-wedding-website/.venv/bin/python` (or after
  `source .venv/bin/activate` from repo root). See handoff Amendments →
  "Per-project Python virtualenv".
- Frontend deps get their own tool — Node/npm, not the venv. Confirm Node
  version choice up front (the handoff doesn't pin one; pick an LTS and
  pin it in the session-6 log). Freeze via `package-lock.json`.
- Every direct dep gets exact-pinned per [[feedback-strict-version-pins]]
  — that means editing `package.json` to remove `^`/`~` prefixes after
  `npm create vite`. Transitive pins come via the lockfile; commit that
  lockfile.

**Work (per handoff `.claude/wedding-site-handoff.md:171-190` and
Session 4's Session 6 handoff):**

1. Scaffold `frontend/` at repo root with Vite + React
   (`npm create vite@<pinned> -- --template react`, or the SWC variant).
2. Configure `vite.config.js`:
   - `build.outDir: '../backend/static/frontend'`
   - `build.emptyOutDir: true`
   - `build.rollupOptions.input: 'src/main.jsx'`
3. Wire the island-mount pattern in `frontend/src/main.jsx` per handoff
   (rsvpRoot + galleryRoot pattern — mount only if the element exists).
4. Create a placeholder `RsvpForm` component (a stub that just renders
   "RSVP island mounted" is fine — this is a scaffolding session, not a
   feature session).
5. Create `backend/templates/base.html` and `backend/templates/rsvp.html`
   (the latter with the `<script type="application/json" id="rsvp-data">`
   props-passing pattern). Wire `TEMPLATES.DIRS` in `base.py` to include
   `BASE_DIR / 'templates'` — currently it's `[]`.
6. Add a `pages` view + URL for `/rsvp/` that renders `rsvp.html` (bare
   minimum — just enough to prove the island renders in a real Django
   template). Real RSVP form logic is Phase 2.
7. `vite build` (writes to `backend/static/frontend/`) then
   `manage.py runserver` — hit `/rsvp/`, see the island mount. Also confirm
   `vite dev` works if you go that route.

**Do not** touch S3, `django-storages`, or `django-vite` yet — this is
purely local build → local Django serves the built assets. Cloud storage
is a Phase 3 concern.

## Open questions / follow-ups

- **Node version + package manager.** Handoff doesn't specify. Session 6
  needs to pick and pin (LTS Node + npm is the default, but `pnpm` and
  `yarn` are options). Recommend LTS Node + npm for minimum surprise.
- **`ModelAdmin` polish.** All six models register with default admin —
  the changelists show "Guest object (1)" etc. instead of names. Adding
  `__str__` + `list_display` + `search_fields` is a ~15-minute win, but
  it's a UX task for whichever session first hits "I actually need to
  manage guests from here." Not blocking.
- **Handoff still uses `apt`/`ubuntu` in the EC2 section** even though
  Amazon Linux 2023 (`dnf`/`ec2-user`) was locked in. Rewriting deferred
  to Phase 4 (per Session 3 handoff).
- **`cost-guard` and `wedding-copy-editor` subagents** — still deferred
  until Phase 3.
