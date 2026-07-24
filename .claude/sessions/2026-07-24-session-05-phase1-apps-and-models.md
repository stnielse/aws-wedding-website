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
now).

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

_(fill as they land)_

---

## Progress

- ⏳ Session log created (this file).
- ⏳ Three apps scaffolded (`rsvp`, `gallery`, `pages`).
- ⏳ Apps added to `INSTALLED_APPS`.
- ⏳ Models written per handoff.
- ⏳ Models registered in admin.
- ⏳ `makemigrations` + `migrate` clean.
- ⏳ Superuser created.
- ⏳ Admin UI verified — every model creatable via `/admin/`.

## Files created / modified this session

_(fill as they land)_

## Session 6 handoff

_(fill at end of session)_

## Open questions / follow-ups

_(fill as they land)_
