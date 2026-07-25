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

- ✅ Session log created (this file).
- ✅ Node 22 LTS installed by user via `brew install node@22` (v22.23.1 landed).
- ✅ `.nvmrc` written at repo root with `22.23.1`.
- ✅ Corepack enabled (`corepack enable`); pnpm pinned to `11.17.0` via the `packageManager` field in `frontend/package.json`.
- ✅ `frontend/` scaffolded via `pnpm create vite@9.1.1 frontend --template react`; direct deps exact-pinned (stripped all `^`/`~`); `pnpm-lock.yaml` generated and committed-worthy.
- ✅ `vite.config.js` set per handoff — `outDir: '../backend/static/frontend'`, `emptyOutDir: true`, `rollupOptions.input: 'src/main.jsx'`, plus stable `entryFileNames: 'assets/main.js'` (see digression on hashing below).
- ✅ `frontend/src/main.jsx` rewritten with the rsvpRoot + galleryRoot island-mount pattern; `RsvpForm.jsx` and `Gallery.jsx` stubs added (both render their props as JSON for visual proof).
- ✅ `backend/templates/base.html` and `backend/templates/rsvp.html` created; `TEMPLATES.DIRS` in `config/settings/base.py` now includes `BASE_DIR / 'templates'`.
- ✅ `/rsvp/` wired via `rsvp/urls.py` (`app_name = 'rsvp'`, `path('', views.rsvp, name='index')`) included at `rsvp/` in `config/urls.py`; view is a bare `render(request, 'rsvp.html')`.
- ✅ `pnpm build` produces `backend/static/frontend/assets/main.js` (190 KB); `runserver` serves the built bundle via `{% static %}`; user visually confirmed the RSVP island mounts at `http://127.0.0.1:8765/rsvp/` with real `csrf_token` in props.
- ✅ `pnpm dev` verified — Vite dev server transforms JSX on the fly with HMR instrumentation intact.
- ✅ Session log finalized (this section).

### Digressions worth remembering

**Vite 8 dev server binds only to `localhost`, not `127.0.0.1`.** Vite's
banner prints `http://localhost:5175/` but `curl http://127.0.0.1:5175/`
hangs indefinitely. `curl http://localhost:5175/` and
`curl http://[::1]:5175/` both work (macOS `/etc/hosts` maps `localhost`
to both). Cost me a 120-second curl timeout on the first `pnpm dev` smoke
test. If we ever run automated frontend smoke tests, always use `localhost`
or pass `vite --host 127.0.0.1` explicitly.

**Vite 8 hashes the entry filename by default.** First build emitted
`main-J_CLQV2d.js` — the hash changes every build, which breaks any static
`<script src="{% static 'frontend/assets/main.js' %}">` reference from a
Django template. Workaround: set `rollupOptions.output.entryFileNames`,
`chunkFileNames`, and `assetFileNames` to unhashed patterns. Cache-busting
is still achievable in production by turning on
`ManifestStaticFilesStorage` in `STORAGES['staticfiles']` — Django hashes
during `collectstatic` and rewrites references. Punting that decision to
Phase 3.

**`STATICFILES_DIRS` was needed.** Django's `AppDirectoriesFinder` only
looks inside app dirs (`rsvp/static/`, etc.), so `backend/static/frontend/`
was invisible to `runserver`. Added `STATICFILES_DIRS = [BASE_DIR / 'static']`
to `base.py`. Session 4's settings had `STATIC_URL` alone, which was enough
until we started producing static assets outside an app dir.

**create-vite@9 defaults to `oxlint`, not eslint.** The Oxc-based linter
ships in the scaffold with an `.oxlintrc.json`. Kept as-is — no reason
to swap to eslint for a one-island frontend. Worth remembering when
reading unfamiliar `pnpm lint` output.

**pnpm noted patch-newer versions than create-vite pinned.** `pnpm install`
reported react 19.2.8 / vite 8.1.5 / oxlint 1.75.0 / plugin-react 6.0.4
are all newer than what create-vite@9.1.1's templates recorded. Left
pinned at create-vite's chosen versions for now — bumping to head is a
follow-up (see open questions).

**Homebrew corepack on Apple Silicon needs no sudo.** `corepack enable`
symlinked `/opt/homebrew/bin/pnpm` → corepack's dispatcher without
permission prompts. Apple Silicon Homebrew is user-owned. On Intel
Homebrew (`/usr/local`) or a Linux box this may require sudo — worth
remembering when we script the EC2 install later.

**Django CSRF cookie is set on the first GET of `/rsvp/`.** The `Set-Cookie`
header in the smoke-test response shows a fresh `csrftoken` was issued
(1-year Max-Age, SameSite=Lax) — the `{% csrf_token %}` template tag
triggered it. Behavior is normal; noting it because the RSVP submit view
in Phase 2 will rely on that cookie's presence for POST validation.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-07-25-session-06-phase1-vite-react-island.md` — this log
- `.nvmrc` — `22.23.1`
- `frontend/` — full scaffold from `pnpm create vite@9.1.1 --template react`, then customized:
  - `frontend/package.json` — rewritten with exact pins and `"packageManager": "pnpm@11.17.0"`
  - `frontend/pnpm-lock.yaml` — generated by `pnpm install` (frozen transitive deps; commit this)
  - `frontend/vite.config.js` — rewritten with build config per handoff + stable filenames
  - `frontend/index.html` — rewritten as a dev harness (bare `rsvp-root` + mock `rsvp-data` JSON)
  - `frontend/src/main.jsx` — rewritten with the two-island mount pattern from the handoff
  - `frontend/src/RsvpForm.jsx` — new; renders "RSVP island mounted." plus props as JSON
  - `frontend/src/Gallery.jsx` — new; symmetric stub for the Gallery island
  - `frontend/.gitignore`, `frontend/.oxlintrc.json`, `frontend/README.md` — kept from scaffold as-is
- `backend/templates/base.html` — minimal layout with `title`/`content`/`scripts` blocks
- `backend/templates/rsvp.html` — extends base, drops `rsvp-data` JSON + `rsvp-root` div + script tag
- `backend/rsvp/urls.py` — `app_name = 'rsvp'`, `path('', views.rsvp, name='index')`

**Deleted from scaffold (demo cruft):**
- `frontend/src/App.jsx`, `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/assets/`
- `frontend/public/favicon.svg`, `frontend/public/icons.svg`

**Modified:**
- `.gitignore` — added `backend/static/frontend/` (Vite build output)
- `backend/config/settings/base.py` — `TEMPLATES.DIRS` now `[BASE_DIR / 'templates']`; added `STATICFILES_DIRS = [BASE_DIR / 'static']`
- `backend/config/urls.py` — imported `include`, added `path('rsvp/', include('rsvp.urls'))`
- `backend/rsvp/views.py` — replaced boilerplate with `def rsvp(request): return render(request, 'rsvp.html')`

**Also touched (not tracked by git):**
- `backend/static/frontend/assets/main.js` — Vite build output (gitignored via the new rule)
- `~/Library/Caches/node/corepack/` — corepack downloaded pnpm 11.17.0 into its cache
- Ephemeral: two runserver background processes (ports 8765 and 5175) started + killed during smoke tests

Per working contract, all `git add` / `git commit` is left to the user.

## Session 7 handoff

**Goal:** Start Phase 2 — the first real user-facing flow. Per handoff
`.claude/wedding-site-handoff.md`, Phase 2 covers the RSVP form
(Guest lookup by token, form submission, RSVP DB write, error paths) and
the Gallery browse view. Session 7 should pick one of those two and
deliver it end-to-end (template + Django view + React island wiring +
POST/GET plumbing + tests). RSVP is the higher-priority flow — recommend
starting there.

**Before touching anything:**

- Read this file (Session 6 log) and Sessions 4-5.
- Re-read the handoff's Phase 2 section for the token-URL scheme, the
  Guest → RSVP relationship, and the expected submit endpoint shape.
- `.venv/bin/python` for all Django commands; `pnpm` (already pinned via
  corepack) for all frontend commands.
- Vite 8 quirk: dev server is `http://localhost:5175/`, NOT
  `http://127.0.0.1:5175/`. If you run automated frontend smoke tests,
  use `localhost` or add `vite --host 127.0.0.1` to the dev script.
- Every direct dep gets exact-pinned per [[feedback-strict-version-pins]].
  Any new frontend dep added via `pnpm add <pkg>` — immediately strip the
  `^` in `package.json` and reinstall.

**Work (concrete steps for Session 7 if you take the RSVP path):**

1. Decide the URL scheme: the handoff mentions token-scoped RSVP URLs
   (`/rsvp/<token>/`). Migrate the current `/rsvp/` route to
   `/rsvp/<token>/`, update the view to `Guest.objects.get(token=token)`
   and pass guest data into `rsvp.html`, and add a `/rsvp/` landing that
   asks for the token or shows an error.
2. Add the submit endpoint: `rsvp/urls.py` — `path('<token>/submit/', views.submit, name='submit')`. The view accepts POST, validates CSRF, creates/updates an `RSVP` row for the guest, returns JSON.
3. Update the `rsvp.html` template's `submitUrl` prop to use
   `{% url 'rsvp:submit' token=guest.token %}` instead of the hardcoded
   `/rsvp/submit/` placeholder.
4. Build out `RsvpForm.jsx` for real: name confirm, attending yes/no,
   plus-one, dietary notes, meal choice, submit button that POSTs to
   `props.submitUrl` with `X-CSRFToken: props.csrfToken`.
5. Add `django-vite` (pinned) if you want HMR-through-Django-runserver.
   Otherwise document the "rebuild + refresh" flow: `pnpm build` writes
   to `backend/static/frontend/`, then reload the Django page. For
   iteration on component internals only, `pnpm dev` against the
   `index.html` harness still works.
6. Tests: at minimum a `TestCase` that GETs `/rsvp/<valid-token>/` (200,
   rsvp-root in HTML) and one that POSTs `submit` with valid + invalid
   payloads.

**Do not** touch S3, `django-storages`, `django-vite` in production, or
the Gallery flow yet — one feature at a time.

## Open questions / follow-ups

- **Bump direct deps to their latest patches?** `pnpm install` flagged
  newer patch versions for react (19.2.8), vite (8.1.5), oxlint (1.75.0),
  and `@vitejs/plugin-react` (6.0.4). We pinned to what create-vite@9.1.1
  chose. Cheap follow-up: `pnpm up react react-dom @vitejs/plugin-react vite oxlint --latest` and update the exact pins in `package.json`.
- **`django-vite` integration.** Deferred this session for a Phase 2+
  decision. If we adopt it, pin the exact version and configure a
  dev/prod switch (dev = read from Vite dev server, prod = read from
  `collectstatic` output).
- **Cache-busting for the built bundle.** Currently `main.js` is
  unhashed. In production, decide between `ManifestStaticFilesStorage`
  (Django-side hashing) or re-enabling Vite hashing + reading Vite's
  `manifest.json` from a templatetag. Phase 3 concern.
- **RSVP submit URL naming.** `rsvp.html` currently hardcodes
  `/rsvp/submit/` in the JSON props. Session 7 must define `rsvp:submit`
  in `rsvp/urls.py` and switch the template to `{% url %}`.
- **`__str__` methods on models.** Still open from Session 5. Not
  blocking; will come up as soon as we admin-edit a Guest.
- **Handoff `apt`/`ubuntu` cleanup.** Still deferred to Phase 4.
- **`cost-guard` and `wedding-copy-editor` subagents.** Still deferred
  until Phase 3.

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
