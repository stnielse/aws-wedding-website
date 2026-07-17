# Session 04 — Phase 1 Django Skeleton

**Date:** 2026-07-17
**Mode:** Execution — first Django scaffold on this project
**Model:** Opus 4.7

---

## Context

Session 3 (`2026-07-15-session-03-phase0-apply.md`) landed Phase 0 — the
CloudFront + S3 maintenance page is live at the apex and `www`, verified with
the 5-check curl block, and the teardown drill passed on the first attempt.
The Session 3 handoff proposed a wide Session 4 covering all of Phase 1
(Django + apps + models + admin + Vite/React + dep pinning) in one shot.

At the start of this session the user narrowed scope: keep Session 4 to the
**Django project skeleton only**, and spread the rest of Phase 1 across
Sessions 5 (apps + models + admin) and 6 (Vite + React). The handoff doc's
"Amendments" section now captures that re-mapping so future sessions can
find it without re-reading this log.

The user also called out that many Python projects live on this machine, so
this repo needs its own virtualenv. That convention is now codified in the
handoff Amendments too.

## Session plan

1. Amend `.claude/wedding-site-handoff.md` — timeline correction, Phase 1
   session split, per-project venv convention.
2. Create `.venv/` at repo root using Homebrew's `python3.12`.
3. Install Django LTS 5.2.x inside the venv, capture the exact patch version.
4. `django-admin startproject config backend` — matches the layout in the
   handoff (`backend/config/…`, `backend/manage.py`).
5. Split `config/settings.py` into `config/settings/{base,local,production}.py`
   per the handoff spec. Wire `manage.py` default to `.local`, `wsgi.py`
   default to `.production`.
6. Split requirements into `backend/requirements/{base,local,production}.txt`
   mirroring the settings split. All versions exact-pinned per
   [[feedback-strict-version-pins]].
7. Verify: `python manage.py migrate --settings=config.settings.local` runs
   clean on SQLite; `runserver` loads `/` (Django welcome) and `/admin/`
   (login page).

No apps get created this session. No AWS. No Vite. That's Sessions 5 and 6.

---

## Decisions locked this session

| Area | Decision |
|---|---|
| Phase 1 split | Session 4 = Django skeleton only; Session 5 = apps + models + admin; Session 6 = Vite + React. Captured in handoff Amendments so it survives beyond this log. |
| Python version | 3.12 via Homebrew (`/opt/homebrew/bin/python3.12`). Django 5.2 LTS supports 3.10-3.13; 3.12 is the mature middle. Not the system 3.8 (anaconda), not the very-new 3.14. |
| Virtualenv location | `.venv/` at repo root, gitignored. Every backend command runs inside it. Per-project isolation is non-negotiable given the user runs many Python projects on this machine. |
| Django version | 5.2 LTS (support window runs through April 2028 — comfortably past our June 2027 teardown per [[project-timeline]]). Pin the exact patch version pip resolves. |
| Requirements structure | `backend/requirements/{base,local,production}.txt` mirroring the settings split. `local.txt` and `production.txt` each start with `-r base.txt` and add environment-specific packages. All exact-pinned per [[feedback-strict-version-pins]]. |
| Settings default per entrypoint | `manage.py` defaults to `config.settings.local` (dev workflow); `wsgi.py` defaults to `config.settings.production` (prod workflow). Neither hardcodes — both read `DJANGO_SETTINGS_MODULE` first and only fall back. |

---

## Progress

- ⬜ Session log created (this file).
- ⬜ `.claude/wedding-site-handoff.md` — Amendments section added.
- ⬜ `.venv/` created at repo root with `python3.12`.
- ⬜ `pip` upgraded inside the venv (baseline is what ships with 3.12).
- ⬜ Django 5.2.x installed, exact version captured.
- ⬜ `backend/` scaffold created via `django-admin startproject config backend`.
- ⬜ Settings module split — `config/settings/{base,local,production}.py`.
- ⬜ `manage.py` + `wsgi.py` wired to the new settings paths.
- ⬜ `backend/requirements/{base,local,production}.txt` written, all exact-pinned.
- ⬜ `python manage.py migrate --settings=config.settings.local` runs clean.
- ⬜ `runserver` loads `/` and `/admin/` locally.

## Files created / modified this session

_(to be filled in as work lands)_

## Session 5 handoff

**Goal:** the three apps and their models — the middle slice of Phase 1.

1. `python manage.py startapp rsvp`, same for `gallery` and `pages` (all
   inside `backend/`).
2. Add each to `INSTALLED_APPS` in `config/settings/base.py`.
3. Write the models exactly as in the handoff
   (`.claude/wedding-site-handoff.md:117-167`):
   - `rsvp/models.py` — `Guest`, `RSVP`
   - `gallery/models.py` — `Photo`
   - `pages/models.py` — `FAQ`, `RegistryLink`, `HotelBlock`
4. Register every model in each app's `admin.py`. `admin.site.register` is
   fine — nothing fancy yet.
5. `makemigrations` + `migrate` (still on SQLite via `config.settings.local`).
6. Confirm each model shows up in `/admin/` and can be created via the admin
   UI.

**Do not** touch `django-storages` or S3 yet — Photo's `ImageField` is fine
against local `MEDIA_ROOT` at this stage. S3 wiring is a Phase 3 (or
late-Phase-2) concern.

## Session 6 handoff

**Goal:** Vite + React scaffold + one mounted island — the last slice of
Phase 1.

1. Scaffold `frontend/` with Vite + React (`npm create vite@… -- --template
   react`). Pin Node deps.
2. Configure `vite.config.js` per handoff (`outDir: '../backend/static/frontend'`,
   `emptyOutDir: true`, `input: 'src/main.jsx'`).
3. Wire the `main.jsx` island-mount pattern from handoff
   (`.claude/wedding-site-handoff.md:171-190`).
4. Mount `RsvpForm` (placeholder component is fine) into a Django template
   (`templates/rsvp.html`) using the `<script type="application/json">`
   props-passing pattern.
5. Run `manage.py runserver` + `vite build` (or `vite dev`) and confirm the
   island renders. That closes out Phase 1.

## Open questions / follow-ups

- Handoff still describes the EC2 setup snippet in `apt`/`ubuntu` terms even
  though we committed to Amazon Linux 2023 (`dnf`/`ec2-user`). Rewriting that
  section is still deferred to Phase 4 (Session 3 handoff, "Deferred to later
  sessions").
- `cost-guard` and `wedding-copy-editor` subagents — still deferred until
  Phase 3 makes them useful.
