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
     with four teaser `<img>` elements. `loading="lazy"`,
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
- [ ] User drops seven source photos into `backend/static/img/engagement/`.
- [ ] `resize_engagement_photos` management command written and run against the drop.
- [ ] `home.html` template edited — hero, arch, photo-break, four teaser tiles now real `<img>`.
- [ ] `site.css` gains fill-slot img rules.
- [ ] `production.py` gains `ManifestStaticFilesStorage`.
- [ ] Manifest verified via scratch `collectstatic`.
- [ ] Smoke test in browser — real photos render, no CLS, nav-reveal still fires, teaser tiles lazy-load.
- [ ] Tests added in `backend/pages/tests.py`.
- [ ] Session log finalized (this section).

### Digressions worth remembering

_(populated as we hit them)_

## Files created / modified this session

_(populated at end of session)_

## Session 10 handoff

_(populated at end of session — expected to hand off the Terraform / django-storages / S3+CloudFront-OAC chunk deferred from this session)_

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
