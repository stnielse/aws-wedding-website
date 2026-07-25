# Session 06 — Phase 1 Vite + React Island

**Date:** 2026-07-25
**Mode:** Execution — Vite + React scaffold + one mounted island in a real Django template
**Model:** Opus 4.7

---

## Context

Session 5 (`2026-07-24-session-05-phase1-apps-and-models.md`) closed out the
Django middle slice: three apps (`rsvp`, `gallery`, `pages`), six models
verbatim from the handoff, admin registration for all six, migrations applied
on SQLite, superuser created, admin end-to-end verified (registry inspection +
ORM round-trip + authenticated GET of every admin URL + manual browser
click-through).

Session 6 is the last slice of Phase 1 per the amended plan
(`.claude/wedding-site-handoff.md` → "Amendments" → "Phase 1 split across
sessions"): stand up the frontend build pipeline (Vite + React), wire the
island-mount pattern from the handoff, drop a real Django template + view at
`/rsvp/`, and prove the built bundle renders inside it.

Still deliberately out of scope: S3 / `django-storages` (Phase 3), HTMX,
`django-vite` templatetag (we'll hardcode a `<script>` for now), real RSVP
form logic (Phase 2), Gallery real content (Phase 2).

## Session plan

1. Install Node 22 LTS via Homebrew (user runs `brew install node@22`).
2. Pin the exact installed Node version to `.nvmrc` at repo root.
3. `corepack enable`, then `corepack use pnpm@<latest-stable>` from
   `frontend/` so the `packageManager` field in `package.json` records the
   exact pnpm version.
4. `pnpm create vite@<pinned> frontend --template react` at repo root; then
   strip `^`/`~` prefixes on direct deps in `package.json` and reinstall so
   `pnpm-lock.yaml` reflects the pinned versions.
5. Overwrite `frontend/vite.config.js` per handoff (lines 206-223) —
   `outDir: '../backend/static/frontend'`, `emptyOutDir: true`,
   `rollupOptions.input: 'src/main.jsx'`.
6. Rewrite `frontend/src/main.jsx` with the rsvpRoot + galleryRoot mount
   pattern; add `RsvpForm.jsx` and `Gallery.jsx` component stubs so the
   unconditional imports resolve.
7. Create `backend/templates/base.html` and `backend/templates/rsvp.html`
   (with the `<script type="application/json" id="rsvp-data">` props-passing
   pattern per handoff); wire `TEMPLATES.DIRS` in `base.py` to include
   `BASE_DIR / 'templates'`.
8. Add a bare-minimum `pages` (or `rsvp`) view + URL for `/rsvp/` that
   renders `rsvp.html`. Note the handoff template references
   `{% url 'rsvp:submit' %}` — decide during work whether to add a
   placeholder namespaced URL in `rsvp/urls.py` or hardcode the URL string
   for now.
9. `pnpm build` (writes to `backend/static/frontend/`), then
   `manage.py runserver` — user hits `/rsvp/` and confirms the island
   mounts. Also confirm `pnpm dev` works for iteration.

Explicitly out of scope: S3, `django-storages`, `django-vite` templatetag,
real RSVP form logic, Gallery real content, HTMX.

---

## Decisions locked this session

| Area | Decision |
|---|---|
| Node runtime | **Node 22 LTS** (current active LTS through Oct 2027 — covers the wedding-site lifetime per [[project-timeline]]). Node 20 rejected because it goes maintenance-only April 2026 and end-of-life before June 2027. |
| Node install path | **Homebrew** (`brew install node@22`). Simplest on macOS; corepack ships with it. Rejected nvm/fnm — no other Node projects in play, no need for a version manager. |
| Node in-repo pin | `.nvmrc` at repo root with the exact minor+patch. Documents the pin for future contributors and CI even though local install is via Homebrew. Standard file most tools honor. |
| Package manager | **pnpm**, pinned via the `packageManager` field in `package.json` (corepack contract). Installed on demand by corepack — no separate global install. `pnpm-lock.yaml` becomes the frozen transitive-dep record; committed. |
| Vite template | `react` (Babel-based). Rejected `react-swc` — SWC's cold-build/HMR wins are meaningful on large codebases; this is one island. Well-trodden path matters more here. |
| Vite build output | Writes into `backend/static/frontend/` per handoff. Django's default `staticfiles` finders (specifically `AppDirectoriesFinder` + `FileSystemFinder`) will pick it up at `collectstatic` time in production. Locally, `runserver` serves it because `DEBUG=True`. |
| Component stubs | Both `RsvpForm.jsx` and `Gallery.jsx` created as stubs. The handoff's `main.jsx` imports both unconditionally at module top; only the `createRoot` calls are gated on element presence. Adding a stub is cheaper than restructuring imports. |
| Vite templatetag | Deferred. The handoff shows `{% vite_asset 'src/main.jsx' %}` (implies `django-vite`), but that package needs pinning + wiring + a dev/prod switch we don't need yet. For this session, `rsvp.html` will use a hardcoded `<script>` tag pointing at the built bundle under `{% static %}`. `django-vite` is a Session-7+ concern once we care about HMR-during-Django-dev. |

---

## Progress

- [x] Session log created (this file).
- [ ] Node 22 LTS installed (user action — `brew install node@22`).
- [ ] `.nvmrc` written with exact installed version.
- [ ] Corepack enabled; pnpm version pinned via `packageManager` field.
- [ ] `frontend/` scaffolded with `pnpm create vite --template react`; direct deps exact-pinned; lockfile committed.
- [ ] `vite.config.js` configured per handoff.
- [ ] `main.jsx` island-mount pattern + `RsvpForm` / `Gallery` stubs.
- [ ] `backend/templates/{base,rsvp}.html` created; `TEMPLATES.DIRS` wired.
- [ ] `/rsvp/` view + URL wired.
- [ ] `pnpm build` runs clean; `runserver` shows the mounted island at `/rsvp/`.
- [ ] `pnpm dev` works for iteration.
- [ ] Session log finalized (files touched, digressions, Session 7 handoff).

### Digressions worth remembering

_(To fill in as we go.)_

## Files created / modified this session

_(To fill in as we go.)_

Per working contract, all `git add` / `git commit` is left to the user.

## Session 7 handoff

_(To fill in at the end.)_

## Open questions / follow-ups

- **`django-vite` integration.** Deferred this session. Will want it in
  Session 7+ to get HMR while iterating on components against a real
  Django-served page. Blocking factor: pin the exact version and decide
  whether to use it in prod (probably not — production reads from
  `collectstatic` output, dev reads from Vite's dev server).
- **`{% url 'rsvp:submit' %}` placeholder.** Whether to define a real
  namespaced `rsvp:submit` URL now (returning HTTP 405/501 as a stub) or
  hardcode a URL string in the template. Real submit lands in Phase 2.
- **`ModelAdmin` polish still open from Session 5.** Not blocking this
  session.
- **Handoff still uses `apt`/`ubuntu` in the EC2 section.** Rewrite
  deferred to Phase 4 per Session 3.
- **`cost-guard` and `wedding-copy-editor` subagents.** Still deferred
  until Phase 3.
