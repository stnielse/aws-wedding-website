# Session 17 — Gallery page: model, pipeline, view, React grid + lightbox

**Date:** 2026-08-13
**Mode:** Execution — feature build
**Model:** Opus 4.7

---

## Context

`/gallery/` still rendered the "Coming soon" placeholder from Session 4
(`backend/pages/views.py:16` → `coming_soon.html`). Session 16's handoff
carried "real gallery page" as an S17+ task with a design pass first.
This session is that pass + build.

State check at session start:

- **Photo model** (`backend/gallery/models.py`): four content fields —
  `image` (`ImageField(upload_to='gallery/')`), `caption`, `alt_text`,
  `order` — plus `uploaded_at`. Zero rows in local DB. Two migrations
  applied.
- **Gallery.jsx** (`frontend/src/Gallery.jsx`): still the print-props
  stub from Session 6.
- **Storage backend**: `production.py` maps `STORAGES['default']` to
  `django-storages`' `S3Storage` with `location='media'`; `local.py`
  falls through to the default `FileSystemStorage` with
  `MEDIA_ROOT=backend/media/`.
- **Static engagement photos** (`backend/static/img/engagement/`): 7
  photos (`hero.jpg`, `arch.jpg`, `break.jpg`, `teaser-1.jpg`
  through `teaser-4.jpg`) plus 4-width derivatives under
  `derivatives/` and a `dimensions.json` sidecar. These stay on the
  home page — they're baked into the design and referenced through
  the `{% engagement_photo %}` tag. Gallery uses a fully separate
  pipeline (S3-backed Photo model), not the static tag.
- **User has 324 photos** on their Mac in
  `/Users/stevennielsen/engagement_photos/` — 5.2 GB of source JPEGs,
  organized as 159 originals + 162 `*-Copy1.jpg` black-and-white
  companions.

### Scope locked with user before starting

1. **Photos source** — `Photo` model + S3 (option 3). Answers the "more
   photos, and ongoing post-wedding" volume; makes admin uploads a
   real path forward rather than a script-only workflow.
2. **Layout** — aspect-preserving masonry-ish grid. Preserves portrait
   vs landscape composition (matches style-guide "photos are the whole
   aesthetic" language).
3. **Lightbox** — full-screen with keyboard nav (arrows, esc), click
   backdrop to close, swipe on touch. `Gallery.jsx` gets real work.
4. **Sort order** — filename-sort strictly. Every `X.jpg` has a
   `X-Copy1.jpg` (b&w pair); pairs must remain adjacent in the
   grid. Sync command assigns explicit `order` values in
   name-sort sequence to enforce this.

### The S3 flow, walked through for the user mid-session

The user asked mid-session for a thorough walk-through of how
`ImageField` interacts with S3 in production. Short version documented
here so a future session doesn't have to re-derive:

- `ImageField` doesn't know or care where bytes go. It calls
  `settings.STORAGES['default']` and asks that backend to write. The
  storage backend differs by env; the model code is identical.
- **Local**: `FileSystemStorage` writes under `MEDIA_ROOT`. `runserver`
  serves the `/media/` prefix (wired this session — see below).
- **Prod**: `S3Storage` writes to the private media bucket at the
  `media/gallery/*` prefix. Bucket name is templated in Terraform
  (`${var.project_tag}-media-${account_id}`) — resolve at runtime with
  `terraform -chdir=infra/phase3 output -raw media_bucket_name`, never
  hardcode. `photo.image.url` returns a CloudFront URL
  (`https://<cloudfront-domain>/media/gallery/*`) via
  `AWS_S3_CUSTOM_DOMAIN`. Bucket is private; only CloudFront's OAC
  identity can read from it.
- **CloudFront is CDN + public HTTPS endpoint, not middleware.** S3
  is the origin.

### Why derivatives up-front, not lazy on request

Originals are 4–8 MB. 324-photo gallery of originals is a >1 GB page
— non-starter. The same `srcset` treatment `static/img/engagement/`
already has: 640/1024/1600/2400 JPGs, `<img srcset sizes>`,
`loading="lazy"` below the fold, explicit width/height. Two paths for
producing derivatives:

- **On admin save (post_save signal)** — user uploads via
  `/admin/gallery/photo/add/`, signal fires Pillow resize, uploads
  the 4 derivatives back to storage. Primary post-wedding path.
- **Local bulk-seed command** — `manage.py sync_gallery_photos
  <source_dir>` for the initial 324-photo dump. Same signal fires
  per Photo, so it reuses the same code path.

Both landed this session.

---

## Decisions locked this session

### URL namespace — `gallery:index` (moved from `pages:gallery`)

| Area | Decision |
|---|---|
| Choice | New `backend/gallery/urls.py` with `app_name='gallery'`, mounted at `/gallery/` in `config/urls.py`. The old `pages:gallery` name (which pointed at the coming-soon placeholder) is retired. |
| Why | The gallery is now more than a coming-soon shell — it's a real app with model, view, template, and JSON API surface. Colocating its URLconf inside the `gallery` app matches how `rsvp` is organized and makes future additions (e.g. `/gallery/photo/<slug>/`) trivial. Three template refs updated as part of the move. |

### Photo model — slug is the derivative filename key, dims cached on the row

| Area | Decision |
|---|---|
| Choice | Added `slug` (unique, auto-populated from filename on save if blank), `width`, `height` fields. Removed the old ordering `['order', 'uploaded_at']` in favor of `['order', '-uploaded_at']` so ties fall to newest-first. `upload_to` moved from `gallery/` to `gallery/originals/` to give derivatives a clean sibling namespace at `gallery/derivatives/`. Model-level helpers `src`, `srcset`, `variant_url(w)` compute URLs via `default_storage.url(...)`, so the same code returns local `/media/…` in dev and the CloudFront URL in prod without branching. |
| Why | Predictable derivative URLs demand a stable, unique key per photo — the slug is that. Filename-based auto-derive keeps the sync flow ergonomic (`DSC03573.jpg` → `dsc03573`); admin lets you type an explicit slug if you'd rather. Width/height on the row means the template can emit `<img width height>` without opening files at render time — critical to avoid layout shift on a 324-photo grid. Original + derivatives in sibling S3 prefixes (`gallery/originals/` and `gallery/derivatives/`) makes debugging + cleanup obvious. |

### Derivatives generated via `post_save` signal, back-filled with `queryset.update()`

| Area | Decision |
|---|---|
| Choice | Two receivers in `gallery/signals.py`. `pre_save` populates slug if blank (slugified filename stem + `-N` counter on collision). `post_save` on `created=True` calls `generate_derivatives(instance.image.name, instance.slug)` from `gallery/services.py`, then back-fills width/height via `Photo.objects.filter(pk=…).update(...)` so it doesn't re-fire `post_save`. Exceptions in derivative generation are caught + logged, not raised — a failed resize shouldn't roll back the Photo row (the row exists, we can regenerate later). |
| Why | Signals let admin uploads and the bulk-seed command share exactly the same code path. `update(...)` bypasses save() to avoid a signal loop that would either infinite-recurse or need a "second-save guard" flag. Exception-swallow-and-log matches the pattern from Session 10's `photo_uploaded` log receiver — the gallery works even if one photo failed to resize. |

### Resize helper is a pure function against a storage abstraction

| Area | Decision |
|---|---|
| Choice | `gallery/services.py::generate_derivatives(source, slug, storage=None, force=False)` accepts either a file-like object or a storage key (string). Idempotent — an existing derivative at the expected key skips (unless `force=True`, in which case it's deleted and rewritten). EXIF orientation is applied via `ImageOps.exif_transpose` before measurement so intrinsic dims match rendered orientation. Same widths + JPEG settings (`quality=82`, `progressive=True`, `optimize=True`) as the existing `resize_engagement_photos` command. |
| Why | A pure function is trivially testable against a `FileSystemStorage(location=tempdir)` — no S3 mock required. Idempotence means the sync command is safe to rerun after adding new photos; skipping existing derivatives is fast enough that a rerun is the natural "have I imported all of them yet?" check. EXIF transpose fixes the phantom rotated-portrait bug I've hit on other projects. |

### `sync_gallery_photos` assigns explicit `order`; view sorts by `[order, -uploaded_at]`

| Area | Decision |
|---|---|
| Choice | Command sorts source files by name, then assigns `order = max(existing_order) + N * ORDER_STEP` where `ORDER_STEP = 10`. Ties across order values fall to newest upload. The view returns `Photo.objects.all()` — the model Meta ordering handles sequence. |
| Why | User's explicit requirement: each `DSCxxxx.jpg` sits next to its `DSCxxxx-Copy1.jpg` partner (color + b&w). Filename sort in Python's default (ASCII) puts `-Copy1.jpg` before `.jpg` because `-` (0x2D) < `.` (0x2E). Assigning `order` in that sequence means the DB is the source of truth for display order — no re-sorting logic needed at render time, and admin edits to `order` on any single row take effect immediately without touching the sync command. `ORDER_STEP = 10` (not 1) so admin reordering can wedge a photo between two adjacent ones without needing a full renumber. |

### Local `/media/` served from `runserver` via a conditional `static()` mount

| Area | Decision |
|---|---|
| Choice | Added a two-line conditional to `config/urls.py`: if `settings.DEBUG` and `MEDIA_URL` is set, append `static(MEDIA_URL, document_root=MEDIA_ROOT)`. Production settings don't set `MEDIA_URL` (media lives on S3), so the branch is a no-op there. |
| Why | Django's `runserver` deliberately doesn't serve `MEDIA_URL` on its own — the security stance is "media serving is your web server's job in prod." In prod that's CloudFront; in local dev we're on `runserver`, so we need the explicit mount to actually see uploaded photos. Guarded on `DEBUG` + `MEDIA_URL` existence so it's a strict local-only path. |

### Aspect-preserving masonry via CSS multi-column, no JS layout

| Area | Decision |
|---|---|
| Choice | `.gallery__grid` uses `column-count: 2/3/4` with `column-gap: 12–14px`; each `.gallery__item` gets `break-inside: avoid; margin-bottom: 12px`. Column count scales at 700px and 1100px viewport breakpoints. Images set `width: 100%; height: auto`, so intrinsic aspect ratio (already captured in `photo.width/height` on the model) is preserved without any calc. |
| Why | The CSS Grid `grid-template-rows: masonry` proposal is Firefox-only + still experimental — cross-browser masonry means either JS (Isotope/Masonry.js — heavyweight for this use case) or CSS multi-column. Multi-column reads top-to-bottom-in-column, which is the accepted browsing pattern for photo galleries and matches how Google Photos, Unsplash, etc. render. Zero-JS layout means the noscript fallback grid uses the same styles. |

### Lightbox is a small React island, not a routed page

| Area | Decision |
|---|---|
| Choice | `Gallery.jsx` owns the grid + lightbox. The grid renders 321 `<button>`s (one per photo); click opens the lightbox at that index. Lightbox: full-screen dark overlay, backdrop-click closes, arrow keys prev/next, esc closes, touch swipe (40px threshold) prev/next. Body scroll locked while open. `<noscript>` fallback in the template renders a plain grid of `<a href=full-image>` — everything works without JS, just no lightbox. |
| Why | A separate `/gallery/photo/<slug>/` view would be honest URL-per-photo but blows up the user's flow: every "next" is a full page load. Lightbox-in-place matches how every photo gallery on the web behaves. Keeping it in `Gallery.jsx` reuses the same island infrastructure as `RsvpForm`; body-scroll lock + focus management is <100 lines of React; no dependency added. |

---

## Progress

- [x] Session log created (this file).
- [x] Photo model: added `slug`, `width`, `height` fields; migration `0003` created + applied.
- [x] `gallery/services.py` — `generate_derivatives()` resize + upload helper with idempotence + EXIF transpose.
- [x] `gallery/signals.py` — pre_save populates slug; post_save generates derivatives and back-fills dims.
- [x] `gallery/urls.py` + `config/urls.py` — new `gallery:index` route; retired `pages:gallery`.
- [x] `gallery/views.py` — real `gallery_index` view returning JSON payload for the React island.
- [x] `templates/gallery.html` extends base with intro + `<script id="gallery-data">` + `<div id="gallery-root">` + noscript fallback.
- [x] `frontend/src/Gallery.jsx` — masonry grid + lightbox (keyboard, swipe, backdrop); pairing into `.gallery__cell` containers so b&w/color pairs stay in the same column; `useColumnCount` + flex-column distribution with `justify-content: space-between` so bottom edges of all columns align.
- [x] `frontend/pnpm build` — outputs to `backend/static/frontend/assets/main.js` (203.5 KB / 63.9 KB gzip after final iteration).
- [x] `backend/static/css/site.css` — appended `~200` lines of gallery + lightbox styles (flex columns for JS grid, multi-column fallback for noscript).
- [x] `config/urls.py` — local `/media/` mount conditional on DEBUG.
- [x] Base + home template refs updated from `pages:gallery` → `gallery:index`.
- [x] `manage.py sync_gallery_photos` command created; smoke-tested with 40-photo subset, then run against full 324-photo source dir. Full sync: 40 skipped (from subset run) + 284 added, all 324 rows land with valid dimensions, 1296 derivative JPGs on disk under `backend/media/gallery/derivatives/`.
- [x] Verified in browser: user confirmed grid + pair adjacency + lightbox all look right on the 40-photo subset; also tweaked the intro copy to their voice ("Wasatch air…&hearts; Steven") — kept.
- [x] Final page render: `/gallery/` returns 200 in ~23ms, HTML payload 342 KB (mostly the embedded 324-photo JSON array), pairs adjacent at `order=10..3240` in `10`-step increments.
- [x] Unit tests written + passing: 15 tests in `gallery/tests.py` (up from 3), full suite 67/67 (down from 68 — dropped the `pages:gallery` coming-soon test since that URL is retired).
- [x] Session log finalized (this step).

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-13-session-17-gallery-page.md` — this log.
- `backend/gallery/services.py` — resize + upload helper.
- `backend/gallery/urls.py` — `gallery:index` URLconf.
- `backend/gallery/management/commands/sync_gallery_photos.py` — bulk-seed command.
- `backend/gallery/migrations/0003_alter_photo_options_photo_height_photo_slug_and_more.py` — model changes.
- `backend/templates/gallery.html` — page template.

**Modified:**
- `backend/gallery/models.py` — added slug, width, height; ordering flipped to `-uploaded_at` tiebreaker; upload_to → `gallery/originals/`; added `src`, `srcset`, `variant_url` helpers.
- `backend/gallery/signals.py` — added `_populate_slug` (pre_save) and `_generate_photo_derivatives` (post_save).
- `backend/gallery/views.py` — replaced empty stub with real `gallery_index` view.
- `backend/gallery/tests.py` — expanded from 3 tests → 15 tests.
- `backend/pages/urls.py` — removed `gallery/` path.
- `backend/pages/views.py` — removed `gallery()` view.
- `backend/pages/tests.py` — removed `test_gallery_returns_200` (URL retired).
- `backend/config/urls.py` — mounted `gallery.urls`; added local `/media/` static mount.
- `backend/templates/base.html` — `pages:gallery` → `gallery:index` (2 refs).
- `backend/templates/home.html` — same rename (1 ref).
- `backend/static/css/site.css` — appended gallery grid + lightbox styles.
- `frontend/src/Gallery.jsx` — replaced stub with full grid + lightbox implementation.

Per working contract, all `git add` / `git commit` / `git push` is left
to the user ([[feedback-git-operations]]). Recommended commit message:

    Session 17 — Gallery page: model, pipeline, view, React grid + lightbox

## Session 18 handoff

Two carry-forward items, both from Session 16's handoff, both still
timing-gated:

### Step 1 — HSTS ramp (timing gate: soak must be clean)

Unchanged from S16 handoff. Earliest window is ~2026-08-19, gated on
the ERROR/CRITICAL log filter staying quiet through then. Ramp
sequence is the same one S16 documented (3600 → 604800 → 31536000 +
INCLUDE_SUBDOMAINS → optional PRELOAD).

### Timing-gated but not "carry forward" — RDS deletion protection

Not a session task; a calendar item. Flip
`aws_db_instance.wedding.deletion_protection` to `true` around T–3 to
T–4 months (2027-01/02) per the criterion in
`infra/phase3/README.md`.

### Prod deployment of the gallery — a separate ~30-minute follow-up

This session got the gallery to green locally with 324 photos. Prod
deploy is straightforward but distinct from the code-only change
that'll fire on next merge:

**1. Merge this branch.** The next `deploy` workflow run picks up the
   new model, migration, view, template, and JSX bundle. When it
   runs, `scripts/deploy.sh` executes `python manage.py migrate` — the
   `0003_alter_photo_options_...` migration adds the slug/width/height
   columns to the prod `gallery_photo` table (empty, so no back-fill
   pain). No user-visible change yet — `/gallery/` renders empty
   ("Photos are on the way.").

**2. Bulk-load photos into prod.** Two paths, pick one:

   **2a. Admin uploads** — log into `https://kaitlynandsteventietheknot.com/admin/`,
       click "Add Photo", pick a file, save. Signal fires on the box,
       generates derivatives, uploads to S3, creates the row. Reliable
       but ~30-40 min of clicking for 324 photos.

   **2b. `sync_gallery_photos` via SSM** — one shot for the whole
       dump. Requires getting the source photos onto the EC2 box
       first. Two sub-steps:

       ```
       # Resolve the media bucket + instance id from Terraform. Do NOT hardcode.
       BUCKET=$(terraform -chdir=infra/phase3 output -raw media_bucket_name)
       INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)

       # Step A: from the Mac, upload source photos to a scratch prefix
       # on the media bucket. Idempotent: rerun after an SSO token
       # expiry safely picks up where it left off.
       aws s3 sync ~/engagement_photos \
           "s3://$BUCKET/scratch/gallery-source/" \
           --exact-timestamps

       # Step B: SSM to the box, sync from that scratch prefix into
       # the Photo model (which will regenerate derivatives at
       # media/gallery/derivatives/ in the same bucket).
       #
       # NOTE: build the SSM parameters as real JSON via jq — do NOT
       # use the CLI's --parameters "commands=[...]" shorthand with
       # escaped quotes. The shorthand parser silently strips the
       # inner quoting on a nested `bash -c "..."`, and the on-box
       # command runs with its arguments truncated. Symptom: SSM
       # invocation reports Failed with stderr like
       # `aws: [ERROR]: the following arguments are required: paths`.
       # Same pattern as `deploy.yml` — pass a proper JSON blob.
       BOX_CMD="sudo -u ec2-user bash -c 'set -e; cd /home/ec2-user/aws-wedding-website && mkdir -p /tmp/gallery-source && aws s3 sync s3://$BUCKET/scratch/gallery-source/ /tmp/gallery-source/ && cd backend && ../.venv/bin/python manage.py sync_gallery_photos /tmp/gallery-source --settings=config.settings.production && rm -rf /tmp/gallery-source'"
       PARAMS=$(jq -n --arg cmd "$BOX_CMD" '{commands: [$cmd]}')

       command_id=$(aws ssm send-command \
           --instance-ids "$INSTANCE_ID" \
           --document-name AWS-RunShellScript \
           --comment "S17 gallery bulk-load" \
           --parameters "$PARAMS" \
           --query 'Command.CommandId' --output text)
       echo "Dispatched: $command_id"

       aws ssm wait command-executed --command-id "$command_id" --instance-id "$INSTANCE_ID"
       aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
         --output json \
         | jq -r '"status: \(.Status)", "----- stdout tail -----", (.StandardOutputContent | split("\n") | .[-60:] | join("\n")), "----- stderr -----", .StandardErrorContent'
       ```

       The EC2 instance role already has S3 read+write on the media
       bucket (verified via `terraform output` in the S12 log). Local
       disk on the t3.micro is ~30 GB — 5.2 GB of source fits with
       room. Delete the scratch prefix from S3 after the sync succeeds
       if you want to keep the bucket tidy.

       **Cleaning up orphaned multipart uploads.** If Step A hit an
       SSO token expiry mid-upload (any `ExpiredToken` on
       `CreateMultipartUpload` / `UploadPart` / `CompleteMultipartUpload`),
       aborted uploads leave orphan parts billed as storage until you
       abort them. `aws s3 sync` re-run doesn't clean these up. Sweep:

       ```
       aws s3api list-multipart-uploads --bucket "$BUCKET" --prefix scratch/gallery-source/ \
         --query 'Uploads[].[Key,UploadId]' --output text \
         | while read -r key upload_id; do
             [ -z "$upload_id" ] && continue
             aws s3api abort-multipart-upload --bucket "$BUCKET" --key "$key" --upload-id "$upload_id"
           done
       ```

       Or, permanent fix: add a lifecycle rule to `infra/phase3/s3_media.tf`
       — `aws_s3_bucket_lifecycle_configuration` with
       `abort_incomplete_multipart_upload { days_after_initiation = 3 }`
       ages any orphans out automatically. Deferred; not blocking.

**3. Verify.** Hit `https://kaitlynandsteventietheknot.com/gallery/`.
   Grid should populate; each `<img src>` will be a CloudFront URL,
   not an S3 URL (verify by right-clicking → Copy image address).

Estimated wall-clock for 2b: ~15 min for `aws s3 sync` (5.2 GB
upload from your Mac), ~10 min for the box-side sync + resize (321
photos × ~2 s each on t3.micro). Do 2b during a low-traffic window
just in case something in the resize path OOMs; the box has 1 GB RAM
and Pillow can spike on large images. If it does OOM, we'll add
swap or run in smaller batches — cross that bridge if we hit it.

## Open questions / follow-ups

*(Carried from S16 unless noted.)*

- **Photo alt-text values** — the pipeline stores `alt_text` but the
  bulk sync leaves it blank; falls back to `caption` (also blank) →
  empty string in the `<img alt>`. This is technically WCAG-compliant
  for decorative images (alt="" is the correct value for pure eye
  candy) but a real gallery of family + friends deserves better. Add
  captions + alt-text via admin as time allows; the model already
  supports it. Session 18 or later.
- **Photo captions on the front page teaser** — the home page pulls
  the four teasers from `static/img/engagement/` via the
  `{% engagement_photo %}` tag, not from the Photo model. Two systems
  now, deliberately: static engagement photos (7 curated, baked into
  design) vs. the full 324-photo dynamic gallery. Should revisit if
  the two ever drift enough to be confusing.
- **`<picture>` mobile crop for hero** — carried from S15.
- **`django-vite`** — still deferred; not blocking.
- **Q1 dietary + Q6 schedule** — still open from Session 7 (RSVP).
- **RDS deletion protection** — flip closer to the wedding
  (2027-01/02).
- **HSTS full ramp** — Session 18+ once soak is clean.
- **Post-wedding gallery additions** — admin uploads (Option 2a in
  the handoff above) is the intended path. Signal handles derivatives
  automatically. No new work.

## Digressions worth remembering

**1. Storage backend "just works" across envs is not accidental.**
The `photo.src` / `photo.srcset` properties call
`default_storage.url(f'gallery/derivatives/{slug}-{w}.jpg')`.
`default_storage` is a proxy that resolves to
`settings.STORAGES['default']` at attribute-access time — so the
identical code returns `/media/gallery/derivatives/…` in local dev
and `https://<cloudfront>/media/gallery/derivatives/…` in production.
The reason `production.py` doesn't set `MEDIA_URL` at all is because
`S3Storage.url()` builds the URL from `custom_domain` +
`location` + key, entirely bypassing the `MEDIA_URL` mechanism. Nice
side effect: the local `static(MEDIA_URL, …)` mount added this
session is guarded on `MEDIA_URL` truthiness, which means a
production `runserver` (if we ever did that for debugging) wouldn't
accidentally try to serve `/media/` from a non-existent local dir.

**2. `Storage.save()` silently uniquifies filenames — worth knowing.**
Trying to write `Photo(image=…).image.save('sunset.jpg', ContentFile(bytes))`
twice does NOT overwrite: the second call renames to
`sunset_<random>.jpg` via `Storage.get_available_name()`. That's why
my first slug-collision test failed — the storage backend had already
renamed the file before slug derivation ran. This matters for the
derivative pipeline: we explicitly `storage.delete(key)` before
`storage.save(key, content)` in the `force=True` branch to actually
overwrite. Same behavior in both `FileSystemStorage` and `S3Storage`.

**4. Bottom-edge alignment across columns needed a layout switch.**
Second review round after the pair fix: with CSS multi-column, all
columns end at slightly different vertical positions because the
`column-fill: balance` algorithm equalizes column HEIGHTS but each
column's content is a stack of variable-height photos — no way to
force exact bottom alignment. Rebuilt as JS-assigned flex columns:
`useColumnCount()` reacts to the same 2/3/4-column breakpoints as
before, cells split into contiguous chunks (`Math.ceil(N/cols)` per
column), each column flex-lays out with `justify-content:
space-between`. First and last cell pin to the column's top/bottom
edges, residual space distributes evenly between the middle cells.
Because photo aspect ratios are similar across the shoot,
equal-count chunks give near-equal natural heights and the residual
`space-between` distribution is small (visually imperceptible per
user's spec). Purely count-based means it's O(N) and stays correct
as photos are added via admin — no per-photo height math or resize
observers required. Fully dynamic: runs the same way for 324 photos
today or 500+ post-wedding.

**5. CSS multi-column masonry redistributes items across columns to
balance heights — pairs can drift out of column.** User caught this
in review: `DSC04289-Copy1` ended up in a different column than
`DSC04289`, breaking the visual pair adjacency the user had
specifically asked for. DOM order was correct (Copy1 at order=1690,
base at order=1700, adjacent as intended), but `column-fill: balance`
kept splitting sequential items into different columns to equalize
column heights. Fix landed same-session: group each pair into a
`.gallery__cell` container with `break-inside: avoid`. The cell is
the atomic unit the browser can place in a column; both photos in a
pair stack vertically inside their cell with an 8px gap. Pairing
logic lives in `Gallery.jsx` (`groupIntoCells(photos)`) because the
input list is already sort-ordered by the server such that `-copy1`
precedes its base (ASCII: `-` < `.`), so a linear scan pairs them
correctly. Singletons (photos whose partner isn't present, e.g. a
base with no `-copy1` companion) become one-photo cells. The
noscript fallback keeps the old flat grid — degrades to "pairs still
in DOM order but may drift across columns" without JS, which is
fine as graceful degradation.

**4. The local `/media/` mount is DEBUG-guarded on purpose.**
Django's `django.conf.urls.static.static(...)` helper is explicitly
NOT for production. In prod, CloudFront serves media directly from S3;
the runserver-based mount would (a) never be exercised since gunicorn
doesn't call it and (b) if it were, would happily read from
`MEDIA_ROOT` (which prod doesn't populate). The DEBUG guard means the
`urlpatterns.append(...)` line is a no-op in prod even if we somehow
imported urls.py under prod settings.

---

## Addendum — Post-merge production bulk-load incident + Option 3 recovery (evening of 2026-08-13)

Merged branch, deployed cleanly, migration applied. Then spent ~4 hours getting 324 photos into prod. Everything below happened between the "wrap up" checkpoint and gallery-live-in-prod.

### What actually landed
- **324 Photo rows in prod RDS**, all with valid `slug`/`width`/`height`, `order` in `[10 … 3240]` step 10.
- **1296 derivative JPGs** in `s3://<media-bucket>/media/gallery/derivatives/` (4 widths × 324 photos).
- **324 originals** in `s3://<media-bucket>/media/gallery/originals/` (uploaded from Mac during the local sync — see below).
- **5.2 GB duplicate copy** of originals also sitting at `s3://<media-bucket>/scratch/gallery-source/` from the earlier failed Step A. Delete before wrap: `aws s3 rm "s3://$BUCKET/scratch/gallery-source/" --recursive`.
- Gallery renders correctly on **apex** URL (`https://kaitlynandsteventietheknot.com/gallery/`).
- Gallery is **broken on www** URL — see "Known issue: www CORS block" below. Fix A deferred to S18.

### The path to get there — five distinct failure classes surfaced in sequence

**1. Guessed bucket name in the handoff.**
Initial handoff wrote `s3://kaitlyn-and-steven-media/...` from memory. Actual bucket is templated in Terraform as `${var.project_tag}-media-${account_id}`, so the real name is `wedding-site-media-633321546572`. User's first `aws s3 sync` hit `NoSuchBucket`. Fixed the log to source via `terraform -chdir=infra/phase3 output -raw media_bucket_name` at use time, and added the "Never guess AWS resource identifiers" rule to `CLAUDE.md`.

**2. SSO token expiry mid-upload of the 5.2 GB source set.**
`aws s3 sync ~/engagement_photos s3://$BUCKET/scratch/gallery-source/` completed ~60% of files before the user's SSO token expired. Failed uploads included in-flight `CreateMultipartUpload`/`UploadPart`/`CompleteMultipartUpload` calls — those left **orphaned multipart parts** in S3 which are billed as storage and never age out without a lifecycle rule. Cleanup recipe:
```
aws s3api list-multipart-uploads --bucket "$BUCKET" --prefix scratch/gallery-source/ \
  --query 'Uploads[].[Key,UploadId]' --output text \
  | while read -r key upload_id; do
      [ -z "$upload_id" ] && continue
      aws s3api abort-multipart-upload --bucket "$BUCKET" --key "$key" --upload-id "$upload_id"
    done
```
Permanent fix (deferred to S18): add `aws_s3_bucket_lifecycle_configuration` to `infra/phase3/s3_media.tf` with `abort_incomplete_multipart_upload { days_after_initiation = 3 }` so this class of leak self-heals.

**3. SSM `--parameters` shorthand silently ate the nested `bash -c "..."` args.**
First on-box `sync_gallery_photos` invocation (Step B) was built with the CLI's `--parameters "commands=[...]"` shorthand and escaped quotes for the nested `sudo -u ec2-user bash -c "..."`. The shorthand parser strips the inner quoting; the on-box command runs with no arguments for `aws s3 sync`. Symptom: SSM reports `Failed` with stderr:
```
aws: [ERROR]: the following arguments are required: paths
```
Fix: build the payload as real JSON via `jq -n --arg cmd "$BOX_CMD" '{commands: [$cmd]}'` and pass with `--parameters "$PARAMS"`. Same pattern `deploy.yml` uses. Patched into the log's Step B recipe.

**4. Log group name — another guessed identifier.**
Diagnostic recipes tried to tail `/wedding/django`; actual group is `/wedding-site/django` (list via `aws logs describe-log-groups`). Same anti-pattern as (1). Second occurrence in one session — extended `CLAUDE.md`'s identifier rule to explicitly name log group names as a member of the "never guess" set.

**5. Pillow OOM on t3.micro (site down).**
Corrected SSM invocation dispatched successfully and ran for ~20 minutes. Then:
- SSM `PingStatus: ConnectionLost`, `StatusDetails: Undeliverable`.
- EC2 status `running`, hypervisor + hardware checks `ok`.
- Site returning nothing in the browser.

Diagnosis: OOM killer took gunicorn, nginx, and the SSM Agent when Pillow's synchronous 6000×4500 JPEG resize exhausted the t3.micro's 1 GB RAM. All three services are systemd-managed with auto-restart but they can't restart if RAM is still starved — the box just sits there `running` from EC2's view, unresponsive to everything.

**Recovery:** `aws ec2 reboot-instances --instance-ids "$INSTANCE_ID"`. ~3 minutes for reboot + service restart to bring `PingStatus` back to `Online` and gunicorn back to `HTTP/2 200`.

### Option 3 — local sync against prod, bypassing the box entirely

Since re-running the same on-box sync would OOM the box again, switched to running `sync_gallery_photos` **locally** on the Mac against **prod RDS via SSM port-forward** and **prod S3 via SSO creds**. Zero new code — the existing management command works unchanged when handed prod-shaped env vars.

**Setup (two terminals):**

Terminal 1 — RDS tunnel (leave running):
```
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)
RDS_HOST=$(aws ssm get-parameter --name /wedding-site/prod/DB_HOST --query 'Parameter.Value' --output text)
aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$RDS_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"15432\"]}"
```

Terminal 2 — install prod deps into local venv, export env vars from SSM Parameter Store, run sync:
```
.venv/bin/pip install -r backend/requirements/production.txt awscrt

export DB_NAME=$(aws ssm get-parameter --name /wedding-site/prod/DB_NAME --query 'Parameter.Value' --output text)
export DB_USER=$(aws ssm get-parameter --name /wedding-site/prod/DB_USER --query 'Parameter.Value' --output text)
export DB_PASSWORD=$(aws ssm get-parameter --name /wedding-site/prod/DB_PASSWORD --with-decryption --query 'Parameter.Value' --output text)
export DB_HOST=localhost
export DB_PORT=15432
export AWS_STORAGE_BUCKET_NAME=$(terraform -chdir=infra/phase3 output -raw media_bucket_name)
export AWS_REGION=$(aws configure get region 2>/dev/null || echo us-east-1)
# Required at settings import time, unused by this run:
export DJANGO_SECRET_KEY=local-bulk-load-not-used-for-signing
export DOMAIN=kaitlynandsteventietheknot.com
export AWS_STATIC_BUCKET_NAME=unused-for-bulk-load

cd backend
../.venv/bin/python manage.py sync_gallery_photos ~/engagement_photos \
    --settings=config.settings.production 2>&1 | tee /tmp/bulk-load.log
```

Wall clock **~25–30 min** for 324 photos on a Mac with reasonable broadband. Each photo: read local file → upload original to prod S3 → Pillow resize to 4 widths → upload 4 derivatives → insert row via tunneled RDS. No box CPU/RAM touched at any point.

**Interleaved output caveat.** Once the sync starts, stderr (JSON-formatted `photo_uploaded`/`photo_derivatives_generated` events from `gallery.signals` under production LOGGING config) writes straight to the terminal, while stdout `add DSCXXX.jpg → id=...` lines lag behind through `tee`'s block buffer. Looks visually broken but both streams describe the same photos in the same order — the stream separation is just a flush-cadence artifact.

### Known issue deferred to S18 — the `www` subdomain gallery is broken by CORS

After the sync landed all 324 photos, gallery worked on `https://kaitlynandsteventietheknot.com/gallery/` (apex) but showed "Loading the gallery…" indefinitely on `https://www.kaitlynandsteventietheknot.com/gallery/` (www subdomain).

**Cause:** `production.py`'s `AWS_STATIC_CUSTOM_DOMAIN` env is set to the apex, so `{% static ... %}` renders links to `https://kaitlynandsteventietheknot.com/static/...` regardless of which origin the page was served from. When the page is loaded from `www.`, the browser sees `www.` → apex requests as **cross-origin** and blocks the JS bundle + fonts under CORS since the response has no `Access-Control-Allow-Origin` header. React never mounts → "Loading the gallery…" persists.

**Fix A (planned for S18 — canonical + cleaner):** CloudFront-level 301 from `www.*` → apex. A CloudFront Function attached to the viewer-request event of the www alias handles this cheaply; Terraform-manageable in `infra/phase3/cloudfront.tf`. Also update the Route 53 www alias if needed. After the redirect is in place, no code change to Django needed — every viewer lands on apex, no cross-origin, no CORS.

**Fix B (not chosen):** Add an `Access-Control-Allow-Origin: https://www.kaitlynandsteventietheknot.com` response header via a CloudFront Response Headers Policy on the `/static/*` and `/media/*` behaviors. Faster to ship but leaves the site with two canonical origins — SEO smell, doubled cache surface.

### Follow-ups for Session 18

- **Fix A: `www` → apex CloudFront redirect** — CF Function, TF change, apply.
- **S3 lifecycle rule to auto-abort orphaned multipart uploads** — `abort_incomplete_multipart_upload { days_after_initiation = 3 }` in `infra/phase3/s3_media.tf`.
- **Photo upload OOM guard.** Admin uploads run the same `post_save` derivative-generation code path on the t3.micro box. A single 30-MB portrait from a modern camera could OOM the same way. Three options:
  - Cheapest: add a `~1 GB` swap file on the box (survives reboots via fstab). Slow when hit but doesn't OOM. Handles the occasional-large-photo case without adding architectural complexity.
  - Middle ground: server-side downscale rejection — cap `Photo.image` on `clean()` to reject sources over N megapixels or N MB, forcing the user to pre-resize.
  - Right answer long-term: move derivative generation to a background job (Celery + Redis, or a simple async worker). Overkill for a wedding site with maybe 100 more photos total over its lifetime.
- **Delete the scratch prefix on S3** — 5.2 GB of duplicated originals from the failed Step A run: `aws s3 rm "s3://$BUCKET/scratch/gallery-source/" --recursive`.
- **Multipart-upload orphan sweep** — see recipe under failure class (2) above, or defer if the lifecycle rule lands first.
- **HSTS ramp** — still gated on soak clean (from S16 handoff, ~2026-08-19 earliest).
- **RDS deletion protection flip** — calendar item, 2027-01/02.

### `CLAUDE.md` amendments landed this session

- **Never guess AWS resource identifiers** — new section under Working Contract. Applies to bucket names, ARNs, instance/security-group/distribution IDs, RDS endpoints, hosted zone IDs, IAM roles, KMS keys, **and log group names** (added after the second guessed-identifier miss in one session). Resolve at use time via `terraform output` or `aws <service> describe-*/list-*`; use `$(…)` placeholders in handoff recipes when the resolver isn't available at write time.

Should extend `CLAUDE.md` further in S18:

- **SSM `--parameters` payload construction** — always build with `jq -n --arg cmd "$CMD" '{commands: [$cmd]}'` and pass with `--parameters "$PARAMS"`. Never use `--parameters "commands=[\"…\"]"` shorthand for anything with nested quotes; the shorthand parser silently strips them. Same pattern `deploy.yml` uses today.

