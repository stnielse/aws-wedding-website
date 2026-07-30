# Session 09 — Home page real photos + ManifestStaticFilesStorage cache-busting

**Date:** 2026-07-30
**Mode:** Execution — Phase 3 prep (no AWS this session)
**Model:** Opus 4.7

---

## Context

Session 8 (`2026-07-29-session-08-phase2-rsvp-flow.md`) closed Phase 2 by
shipping the household-oriented RSVP flow, per-guest form + editable receipt,
the sticky-nav reveal, and 21 tests. It handed Session 9 a three-chunk Phase 3
opener: cloud storage for the gallery, real `<img>` on the home page, and a
cache-busting decision.

Session 9 takes the two chunks that are entirely local — the home page
placeholders and the cache-busting scheme — and defers the Terraform /
django-storages / CloudFront OAC chunk to Session 10. Rationale:

- **Nothing about the four editorial slots on the home page needs S3** —
  they're template-bound site chrome, not gallery-managed uploads, so they
  belong in the staticfiles pipeline where `{% static %}` + Manifest hashes
  them without any storage-backend changes.
- **Cache-busting is a small, contained decision** that doesn't compound with
  Terraform work, so it's cleaner to land here and let the Session 10 S3 pivot
  inherit an already-hashed staticfiles setup.
- **Terraform is a long-blocking run** (per [[feedback-long-running-commands]])
  and permanently destroys the phase 0 maintenance module — worth its own
  session with fresh eyes.

When this session lands, the site will have:

- Real engagement photos in all four home page slots (hero, story arch
  portrait, photo-break, four teaser tiles) — `<img>` with `srcset` at
  640/1024/1600/2400, `loading="lazy"` below the fold, explicit
  `width`/`height` to lock CLS
- Pillow-driven resize pipeline emitting the four srcset variants from a
  single high-res source per slot — a `manage.py` command, so it's rerunnable
  when photos are swapped
- `ManifestStaticFilesStorage` wired in `production.py` — `main.js`,
  `site.css`, `nav-reveal.js`, and every engagement photo get hash-suffixed
  URLs at `collectstatic` time; browser caches invalidate cleanly on content
  change
- Tests: at least one asserting `<img>` renders with expected `src`/`srcset`
  attributes in the four home slots (protects against future `img-slot` regressions)

Out of scope this session (deferred to Session 10+):

- **`django-storages` + S3 media bucket** — the whole Phase-3-per-handoff
  Terraform lift. Session 10.
- **Real gallery page** — `/gallery/` stays as `coming_soon.html`. The Photo
  model + admin ImageField work today against local `MEDIA_ROOT`; a gallery
  UI is Phase 3 tail material.
- **`<picture>` art direction for hero mobile crop** — the design mock says
  "16:9 → 3:4 on phone". CSS `object-fit: cover` on a 16:9 source lands close
  enough; a proper `<picture>` with a mobile-cropped source is a follow-up if
  the crop looks wrong on device.
- **AVIF / WebP alternates** — JPEG only this session. Modern browsers all
  accept JPEG; adding AVIF is a size-savings pass, not correctness.

## Session plan

1. Create this session log (in progress).
2. **Photo drop.** User drops seven files into
   `backend/static/img/engagement/`: `hero.jpg`, `arch.jpg`, `break.jpg`,
   `teaser-1.jpg` through `teaser-4.jpg`. Highest-res source available per
   slot; session generates the srcset variants. Directory pre-created this
   session.
3. **Resize pipeline.** New `backend/gallery/management/commands/resize_engagement_photos.py`
   — Pillow reads each source in `backend/static/img/engagement/`, emits
   `hero-640.jpg`, `hero-1024.jpg`, `hero-1600.jpg`, `hero-2400.jpg` (and same
   for the other six slots) into `backend/static/img/engagement/derivatives/`.
   Skip if a derivative is newer than its source. Quality 82, progressive,
   `Image.LANCZOS` resampling.
   - Command lives under `gallery` app (closest domain match — it deals with
     photo processing, even if these particular photos are template-bound
     rather than `Photo` model rows).
   - Idempotent — safe to rerun.
   - Emits width/height of each source to a JSON sidecar
     (`derivatives/dimensions.json`) so templates can hardcode `width` and
     `height` without loading Pillow at request time.
4. **Templates.** Edit `backend/templates/home.html` in four spots:
   - **Hero** (line 9-25): replace the `.hero__label` placeholder div with a
     real `<img class="hero__img" src=".../hero-1600.jpg" srcset=".../hero-640.jpg 640w, ...-1024.jpg 1024w, ...-1600.jpg 1600w, ...-2400.jpg 2400w" sizes="100vw" width=... height=... alt="Kaitlyn and Steven at sunset in the canyon">`. `loading="eager"` (above the fold). `.hero__scrim` stays.
   - **Story arch portrait** (line 53-55): replace `.img-slot--3-4-arch` with
     the arch `<img>`. `loading="lazy"`, `sizes="(min-width: 900px) 460px, 100vw"`.
   - **Photo break** (line 97-99): replace the section's text content with a
     full-bleed `<img>`. `loading="lazy"`. Preserve `.photo-break` structure
     for the aspect-ratio wrapper.
   - **Photos teaser** (line 141-146): replace the four `.img-slot--1-1` divs
     with four teaser `<img>` elements in **3:4 vertical** (not 1:1 as the
     original mock; the dropped photos are vertical). `loading="lazy"`,
     `sizes="(min-width: 900px) 22vw, 45vw"`.
5. **CSS pass.** Add `.hero__img`, `.photo-break img`, `.story__image img`,
   `.photos-teaser__grid img` rules to `backend/static/css/site.css`:
   `width: 100%; height: 100%; object-fit: cover;` for the fill slots.
   Existing `.img-slot` rules stay (still used elsewhere) — no removal.
6. **`ManifestStaticFilesStorage`.** In `backend/config/settings/production.py`:
   ```python
   STORAGES = {
       'default': {'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage'},
       'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
   }
   ```
   Only change is the `staticfiles` line. Local dev keeps the default (no
   hashing) because `local.py` doesn't declare `STORAGES` at all.
7. **Verify Manifest works** with a scratch `collectstatic` run against
   production settings + a temp `.env` — confirms `staticfiles/staticfiles.json`
   materializes and `main.js` gets hashed. Roll back afterward (delete the
   scratch `staticfiles/` dir; the real one gets generated on deploy).
8. **Smoke test.** `pnpm build` + `runserver` + browser click-through: home
   page renders with real photos, hero above the fold sharp on retina,
   teaser tiles lazy-load on scroll, no CLS jump, nav-reveal still fires when
   scrolling past hero. Network tab: `main.js` and engagement photos served
   with `Cache-Control` on production (verified via `runserver
   --settings=config.settings.production` with staticfiles collected).
9. **Tests (penultimate step per working contract).** Extend
   `backend/pages/tests.py` (or create if missing) with:
   - `GET /` returns 200
   - Response contains `<img` for hero and at least one teaser slot
   - Response's hero `<img>` has both `src` and `srcset` attributes
   - No `img-slot--16-9` / `img-slot--3-4-arch` divs remain on home
     (regression fence against a future revert)
10. Finalize this log.

---

## Decisions locked this session

### Where photos live in the repo

| Area | Decision |
|---|---|
| Path | `backend/static/img/engagement/` for high-res sources; `backend/static/img/engagement/derivatives/` for the emitted 640/1024/1600/2400 variants. |
| Not `media/gallery/` | These are editorial site chrome bound to specific template slots — not user-managed content. They belong in staticfiles so `{% static %}` + Manifest hashing applies for free. The `Photo` model + `media/gallery/` upload path stays reserved for the full gallery page (Session 10+). |
| Format | JPEG only this session. Progressive, quality 82. AVIF/WebP alternates are a future optimization, not correctness. |
| Source filenames | `hero.jpg`, `arch.jpg`, `break.jpg`, `teaser-1.jpg` through `teaser-4.jpg`. Fixed set — the resize command hardcodes them so a typo in a filename fails loudly rather than silently skipping. |

### Cache-busting

| Area | Decision |
|---|---|
| Choice | `ManifestStaticFilesStorage` over Vite hashing + manifest read. |
| Why | Smaller surface area: one settings line in `production.py`, zero Vite config change, zero new templatetag. Vite's manifest.json path is worth it later if we ever code-split; today we ship one `main.js`, so the extra plumbing has no payoff. Django-side hashing also naturally covers CSS, JS, *and* the seven engagement JPEGs in one pipeline. |
| Scope | Production only — `local.py` doesn't declare `STORAGES`, so dev keeps unhashed URLs and skips the manifest read (which would error on missing files). |
| Trade-off | `collectstatic` becomes a required deploy step (already was per the handoff's deploy sketch). If we ever want dev to match prod behavior, a two-line addition to `local.py` flips it on locally too. |

### Photos as dropped (2026-07-30)

| Slot | Source dimensions | Source ratio | Display slot ratio | Notes |
|---|---|---|---|---|
| hero | 5680×3787 | 3:2 (1.50) | 16:9 → 3:4 on phone (CSS) | Sides get cropped a little via `object-fit: cover`. |
| arch | 4672×6541 | ~5:7 (0.71) | 3:4 (CSS) | Nearly flush; minor top/bottom trim. |
| break | 4718×3646 | 13:10 (1.29) | 16:9 (CSS) | Sides get cropped a bit via `object-fit: cover`. |
| teaser-1 | 4257×5509 | ~3:4 (0.77) | 3:4 | Clean. |
| teaser-2 | 4070×6105 | 2:3 (0.67) | 3:4 | Modest top/bottom trim via `object-fit: cover`. |
| teaser-3 | 4672×6541 | ~5:7 (0.71) | 3:4 | Nearly flush. |
| teaser-4 | 4672×6046 | ~3:4 (0.77) | 3:4 | Clean. |

Teaser slot switched from **1:1** (design mock) to **3:4 vertical** (matches
dropped photos; the mock is a wireframe placeholder, not authoritative on
crop). Four vertical tiles at 22vw each on desktop reads as a photo strip.

### Srcset breakpoints

| Area | Decision |
|---|---|
| Widths | 640 / 1024 / 1600 / 2400. From the Session 8 handoff verbatim. Covers phone (640), small tablet (1024), laptop (1600), retina laptop / 4K (2400). |
| `sizes` per slot | Hero `100vw`. Story arch `(min-width: 900px) 460px, 100vw`. Photo break `100vw`. Teaser tiles `(min-width: 900px) 22vw, 45vw`. Chosen from actual CSS constraints in `site.css` — the `.story__image .img-slot { max-width: 460px }` rule anchors the arch calculation. |
| `loading` | `eager` on hero only (above the fold); `lazy` on the other six slots. `decoding="async"` on all. |
| `width` / `height` | Hardcoded from `dimensions.json` emitted by the resize command. Prevents CLS. Values are of the intrinsic source dimensions — browser scales via CSS. |

### Resize pipeline as a management command

| Area | Decision |
|---|---|
| Where | `backend/gallery/management/commands/resize_engagement_photos.py`. `gallery` app because it's the closest domain match — even though these particular photos don't hit the `Photo` model, image processing conceptually belongs there. |
| Idempotent | Skip a derivative if its mtime is newer than the source. Rerunning after a photo swap regenerates only the changed slot. |
| Not a build hook | Not wired into `pnpm build` or a `pre-commit` hook this session. Manual `manage.py resize_engagement_photos` after any photo drop. Wiring it into CI is Phase 4 territory. |
| Dimensions sidecar | `derivatives/dimensions.json` — `{ "hero": {"width": 2400, "height": 1350}, ... }`. Templates read via a context processor or a template tag. Decision here: **template tag**, since only the home page needs it; a context processor would run per-request site-wide. |

### Out-of-scope defer log

- **Q1 dietary + Q6 schedule** — still open, still not this session's problem.
- **`<picture>` art direction for hero mobile crop** — the mock says 16:9 → 3:4 on phone. CSS `object-fit: cover` on a 16:9 source approximates it; revisit if the on-device crop reads wrong.
- **AVIF / WebP variants** — file-size optimization, not correctness.
- **Full gallery page** — the `/gallery/` route still renders `coming_soon.html`. Session 10+ once real S3 storage is live.
- **`django-vite`** — still deferred.
- **CI-integrated resize step** — Phase 4 concern.

---

## Progress

- [x] Session log created (this file).
- [x] User dropped seven source photos into `backend/static/img/engagement/` (5680×3787 hero, 4672×6541 arch, 4718×3646 break, four vertical teasers 4070–4672 wide).
- [x] `resize_engagement_photos` management command written and run — 28 derivatives generated (7 slots × 4 widths) plus `dimensions.json` sidecar.
- [x] `pages/templatetags/engagement_photos.py` exposes `{% engagement_photo <slot> %}` returning `{src, srcset, width, height}` via `staticfiles_storage.url` (Manifest-aware at request time).
- [x] `home.html` edited — hero (eager, `fetchpriority="high"`), story arch (lazy), photo-break (lazy, empty alt as decorative), four teaser tiles (lazy). All `img-slot` placeholder divs on home removed.
- [x] `site.css` gains `.hero__img`, `.story__img`, `.photo-break__img`, `.photos-teaser__img` rules; `.hero__label` (design annotation placeholder) removed; `.photo-break` shed its striped background + text-content padding.
- [x] `production.py` swapped `StaticFilesStorage` → `ManifestStaticFilesStorage`. `local.py` untouched (still serves unhashed).
- [x] Manifest verified via scratch `collectstatic --settings=config.settings.production --clear --noinput`: 171 files copied + post-processed; `staticfiles.json` maps each engagement derivative + `main.js` + `site.css` + `nav-reveal.js` to a content-hashed filename. Scratch output cleaned.
- [x] Smoke test in browser — user confirmed real photos render correctly after the flex/grid `<img>` `min-width: auto` fix documented below. Nav-reveal + hero legibility + all four slots verified.
- [x] Tests added in `backend/pages/tests.py` — 10 tests across 2 classes. Full suite: 31 pass (21 rsvp + 10 pages).
- [x] Session log finalized (this section).

### Digressions worth remembering

**Teaser slot went from 1:1 to 3:4.** The design mock showed four square tiles; the dropped engagement photos are all vertical (2:3 to 3:4 range). Rather than square-cropping and losing composition, we switched the CSS `aspect-ratio` on `.photos-teaser__img` to `3 / 4`. Reads as a photo strip on desktop (four ~264×352 tiles at ~22vw), 2×2 on mobile. Session 10+ can revisit if the visual weight feels off.

**Hero source is 3:2 (5680×3787), not the mock's 16:9.** `object-fit: cover` in `.hero__img` crops the sides in the 16:9-shaped slot. Visually indistinguishable from a native 16:9. Same story for `break.jpg` (13:10). Neither warrants re-shooting; the design mock's aspect specs are slot-intents, not source-file requirements.

**`ManifestStaticFilesStorage` collectstatic writes both hashed and unhashed copies.** So a `collectstatic` produces `hero-2400.jpg` AND `hero-2400.<hash>.jpg` in `STATIC_ROOT`. Django serves the hashed one via `{% static %}` + the manifest; the unhashed copy is a fallback and takes disk space. For seven engagement photos × 4 widths that's ~28MB of duplication on EC2 — negligible for our footprint but worth remembering when Session 10 wires S3 (double the PUTs per deploy unless we set `keep_intermediate_files=False` on the storage backend or filter uploads).

**`dimensions.json` is read via `BASE_DIR`, not `{% static %}`.** The template tag opens `settings.BASE_DIR / 'static' / 'img' / 'engagement' / 'derivatives' / 'dimensions.json'` at Python import time (module-level cache) rather than through the staticfiles URL system. Two consequences: (1) the running app needs the source `static/` dir on disk, which our EC2 layout gives it for free; (2) changes to `dimensions.json` require a Python reload (or Gunicorn restart) to pick up. Fine for content-frozen photos; if the photo set ever churns rapidly, add a management command that emits Python instead of JSON, or drop the module-level cache.

**`fetchpriority="high"` on hero** is a modern browser hint for the LCP element. Chrome/Edge/Safari support it; older browsers ignore it silently. Zero downside to include.

**No dev-server hashing.** `local.py` doesn't declare `STORAGES`, so it inherits Django's default `StaticFilesStorage` (unhashed URLs). Dev matches prod for markup shape but not for URLs — a `{% static %}` returns `/static/img/engagement/derivatives/hero-1600.jpg` in dev and `/static/img/engagement/derivatives/hero-1600.<hash>.jpg` in prod. Not worth flipping Manifest on locally: `collectstatic` would need to run on every static-file change, which kills iteration.

**Flex/grid `<img>` with intrinsic HTML dimensions needs `min-width: 0`.** First browser smoke test: the arch portrait + four teaser tiles rendered "insanely long and skinny" — object-fit cropping only the middle of the source. Root cause is a classic gotcha: `<img>` elements inside a flex parent (`.story__image`) or grid parent (`.photos-teaser__grid`) inherit `min-width: auto` in the inline axis, and for images the `auto` value resolves to the source's intrinsic pixel width. Our engagement JPEGs have `width="4672"` intrinsic attributes, which forced the flex/grid item to refuse to shrink below 4672px — the `aspect-ratio: 3/4` computation then produced a 4672 × 6229 element that got scrunched by the parent's inline-size cap into a skinny tall silhouette with `object-fit: cover` hiding everything but a vertical stripe. Fix: `min-width: 0` on both `.story__img` and `.photos-teaser__img` (also added `height: auto` for good measure). Two lines each. Locking as a rule: **any `<img>` sized via CSS `aspect-ratio` inside a flex or grid parent needs `min-width: 0`** — the intrinsic HTML width attribute we set for CLS prevention is exactly what triggers the bug. Also worth noting: this only surfaces when the source's intrinsic width is significantly larger than the layout column, which is our case with 4000-5000px+ sources.

**Manifest-hashed dev is off, but stale browser CSS still bites in dev.** The above bug was compounded by the user's browser holding a cached copy of `site.css` from Session 8, so the first two edit passes didn't take effect until Cmd+Shift+R. Django's runserver serves static files without strong cache-control, so the browser's heuristic cache decides. Not worth wiring cache-busting in dev — just remember to hard-refresh after CSS changes when iterating.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-07-30-session-09-home-photos-and-manifest.md` — this log
- `backend/static/img/engagement/` (directory) — user-populated with 7 source JPEGs
- `backend/static/img/engagement/derivatives/` — 28 resized JPEG variants + `dimensions.json`, generated by the resize command
- `backend/gallery/management/__init__.py`
- `backend/gallery/management/commands/__init__.py`
- `backend/gallery/management/commands/resize_engagement_photos.py` — Pillow-driven, idempotent, JPEG 82 progressive, Lanczos resample
- `backend/pages/templatetags/__init__.py`
- `backend/pages/templatetags/engagement_photos.py` — `{% engagement_photo <slot> as x %}` template tag; module-level dimensions cache

**Modified:**
- `backend/config/settings/production.py` — `STORAGES['staticfiles']['BACKEND']` → `ManifestStaticFilesStorage`
- `backend/templates/home.html` — added `{% load engagement_photos %}`; replaced hero placeholder div with `<img class="hero__img">` (eager, fetchpriority high); replaced `.img-slot--3-4-arch` with `<img class="story__img">`; replaced `.photo-break` text content with `<img class="photo-break__img">`; replaced four `.img-slot--1-1` placeholders with four `<img class="photos-teaser__img">`; removed the "Four square tiles" annotation copy
- `backend/static/css/site.css` — dropped `.hero__label` block; added `.hero__img`, `.story__img`, `.photo-break__img`, `.photos-teaser__img` rules; `.photo-break` shed its striped background + monospace label padding; `.story__img` and `.photos-teaser__img` include `min-width: 0` + `height: auto` to defuse the flex/grid `<img>` intrinsic-width bug documented under Digressions
- `backend/pages/tests.py` — replaced the empty scaffold with `HomePageTests` (7 tests) + `ComingSoonPagesTests` (3 tests)

**Also touched (not tracked by git):**
- Ephemeral: dev server + scratch `collectstatic` under prod settings; `staticfiles/` written then removed

Per working contract, all `git add` / `git commit` is left to the user.

## Session 10 handoff

Session 10 picks up the Phase 3 (per handoff phase numbering) Terraform work
deferred from Session 9. Prep list:

1. **New `infra/` module** (not `infra/phase0/`, which stays as-is until we cut over).
   Terraform for the real S3 media bucket, the CloudFront distribution with
   two origins (S3 for `/media/*`, EC2 for everything else), Route 53 alias
   record, ACM cert attach (already Issued in us-east-1). Per Session 8's
   handoff, use OAC (Origin Access Control), not OAI. `terraform destroy`
   must be clean.
2. **`django-storages` runtime check.** `production.py` already declares
   `storages.backends.s3boto3.S3Boto3Storage` as `STORAGES['default']`.
   Once the bucket is up, verify a `Photo` upload through Django admin lands
   in S3 and `Photo.image.url` returns a CloudFront URL. Local dev still
   uses filesystem (`local.py` doesn't declare `STORAGES`).
3. **`ManifestStaticFilesStorage` + S3 static.** Session 9 wired Manifest for
   the staticfiles backend (still local disk in `production.py`). Two paths
   for Session 10:
   - **A. Static stays on EC2** behind nginx, media goes to S3+CloudFront.
     Simpler; matches the handoff's default sketch.
   - **B. Static also goes to S3+CloudFront** (`storages.backends.s3boto3.S3StaticStorage`),
     with `ManifestFilesMixin` for hashing. More complex, avoids nginx serving
     large `staticfiles/` (110+ files including engagement JPEGs).
     Given the engagement JPEG total, B is probably right — decide up front.
4. **Phase 0 teardown.** After the new module applies clean, `terraform
   destroy` `infra/phase0/`. Update the phase0 README to note the module is
   retired. Prevents the phase0 bucket + distribution from accruing charges
   (small, but real).
5. **DNS cutover.** Route 53 alias flips from phase0's CloudFront to the new
   distribution. Instant TTL because it's an alias, but plan the order:
   new distribution deployed and healthy → alias update → phase0 destroy.
6. **Cost check** after apply. Verify aggregate spend still targets
   <$5/month per the handoff's amendment.
7. **Optional follow-ups** noted in Session 9's digressions:
   - `keep_intermediate_files=False` on the storage backend if the doubled
     `staticfiles/` size annoys us on S3.
   - Wire `resize_engagement_photos` into a CI step so a re-drop doesn't
     require manual invocation before deploy.

Before touching anything in Session 10:

- Read this file (Session 9), plus Session 8's Terraform / S3 handoff notes.
- **Python:** `/Users/stevennielsen/aws-wedding-website/.venv/bin/python`.
- **Frontend:** `pnpm` via corepack from `frontend/`.
- **Runserver:** 8765. **Vite dev:** `http://localhost:5175/`, not `127.0.0.1`.
- Every direct Terraform provider / module version gets exact-pinned per [[feedback-strict-version-pins]].
- Tests are the penultimate step per the working contract.
- Long-running `terraform apply` / `destroy` handed to the user per [[feedback-long-running-commands]].

## Open questions / follow-ups

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Photo alt-text values** — the seven engagement photos need real alt text
  before the site goes live. Placeholder strings this session; final copy is
  a couple-review task (Kaitlyn's better at it than me).
- **`<picture>` mobile crop** for hero — revisit after seeing the CSS
  approximation on a real device.
- **`django-vite`** — still deferred.
- **Real gallery page** — Session 10+.
- **Handoff `apt`/`ubuntu` cleanup** — Phase 4.
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3.
