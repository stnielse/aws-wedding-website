# Session 14 — Phase 3: CloudFront + DNS cutover + phase 0 destroy

**Date:** 2026-08-05
**Mode:** Execution — public HTTPS cutover
**Model:** Opus 4.7

---

## Context

Session 13 (`2026-08-04-session-13-phase3-ec2-and-ci-continued.md`)
landed the EC2 web tier, CI workflow, and first real deploy. Site
currently serves HTTP-only on the EIP (`http://32.199.50.156/`) with
apex + www DNS still pointing at the **phase 0 maintenance
CloudFront distribution**. Terraform state: 40 resources across
phase 3, 8 resources in phase 0.

Session 14 does the public-facing cutover — the moment
`https://kaitlynandsteventietheknot.com` starts serving the real
site:

1. Build a new CloudFront distribution in phase 3 with three origins
   (media S3, static S3, EC2 EIP) and three path-based cache
   behaviors (`/media/*`, `/static/*`, default).
2. Attach OAC-scoped bucket policies to media + static.
3. Update production settings so Django trusts CloudFront's
   `X-Forwarded-Proto` header and sets `Secure`/`SameSite` cookies.
4. Publish updated SSM params so django-storages serves media +
   static URLs on the apex domain (via the new distribution).
5. Migrate Route 53 apex/www records from phase 0 into phase 3
   (state rm + `import` blocks — no DNS outage).
6. Once verified, destroy the phase 0 stack (maintenance CF + S3 +
   OAC) and turn on branch protection on `main`.

**Renumber note.** No renumbering needed. Session 15 remains
"CloudWatch Agent + log groups + retention + ERROR alarm + GitHub
Actions OIDC deploy role + `deploy.yml`."

## Session plan

1. Create this session log (in progress).
2. Add `acm_certificate_arn` and `hosted_zone_id` variables to
   `infra/phase3/variables.tf`; append values to gitignored
   `infra/phase3/terraform.tfvars`; document in
   `terraform.tfvars.example`.
3. Write `infra/phase3/cloudfront.tf` — 2 OACs, 1 distribution with
   3 origins + 3 cache behaviors, custom error pages that stay
   transparent (no rewrite).
4. Uncomment / add `aws_s3_bucket_policy` on media + static
   (`AllowCloudFrontOACRead` scoped to distribution ARN).
5. Extend `infra/phase3/outputs.tf` with CloudFront outputs.
6. Update `backend/config/settings/production.py`:
   - `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
   - `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`
   - `CSRF_TRUSTED_ORIGINS` from `CSRF_TRUSTED_ORIGINS` env var
     (comma-separated, mirrors ALLOWED_HOSTS parsing)
   - `SECURE_SSL_REDIRECT = False` (CloudFront enforces
     redirect-to-https at the edge; a Django-side redirect would
     compete)
   - Storage `AWS_LOCATION = 'media'` / `'static'` so S3 keys carry
     the same prefixes as CloudFront path patterns.
   - Add matching tests in `backend/config/tests.py`.
7. Add SSM params for the new CloudFront-facing settings:
   `AWS_S3_CUSTOM_DOMAIN` and `AWS_STATIC_CUSTOM_DOMAIN` (both =
   apex domain), `CSRF_TRUSTED_ORIGINS`.
8. Write `infra/phase3/route53.tf` with `import` blocks pointing at
   the four existing Route 53 records; alias targets swap to the
   new phase 3 distribution on apply. State-rm from phase 0 as a
   separate manual step before apply.
9. `terraform -chdir=infra/phase3 validate` + `fmt -diff` +
   non-ASCII grep of TF description fields (per
   [[feedback-aws-ascii-only-descriptions]]).
10. `.venv/bin/python manage.py test` from `backend/` — expect
    ≥47 old tests plus new CSRF/SSL/storage-location tests to pass.
11. Hand user (a) `aws sso login`, (b) `terraform state rm` for
    phase 0 records, (c) `terraform plan -out=tfplan` +
    `apply tfplan` in phase 3
    (per [[feedback-long-running-commands]]). Expected ~15 new
    resources + 4 imports + 2 policy attaches.
12. Verify HTTPS end-to-end via `curl` + browser.
13. Migrate any existing media objects to the `media/` prefix (a
    small `boto3` copy loop) OR — if bucket is empty — skip.
14. Hand user `terraform destroy` on phase 0 (~15–30 min for
    CloudFront disable+delete).
15. Draft branch-protection instructions for user to apply in
    GitHub Settings.
16. Finalize this log.

---

## Decisions locked this session

### CloudFront: single distribution, three path-based behaviors, apex-fronted

| Area | Decision |
|---|---|
| Choice | One CloudFront distribution with `/media/*` → media S3, `/static/*` → static S3, default → EC2 origin. Both S3 origins accessed via OAC. Apex + www are the only aliases. |
| Why | Simpler than three distributions + subdomains; matches Session 12's plan verbatim; keeps all URLs on the wedding domain; one ACM cert covers everything. Traffic is well under free-tier, so a single-distribution price class (`PriceClass_100` — US/EU only) is fine. |

### django-storages `AWS_LOCATION` set for both backends

| Area | Decision |
|---|---|
| Choice | Media backend gets `AWS_LOCATION = 'media'`; static backend gets `AWS_LOCATION = 'static'`. So S3 keys become `media/photos/foo.jpg` and `static/style.abc123.css`, matching CloudFront's path patterns 1:1. |
| Why | Without a prefix, S3 keys would be at bucket root and CloudFront's `/media/*` cache behavior couldn't find them. Options were (a) `AWS_LOCATION` prefix in-app, (b) CloudFront function to strip `/media/` on origin request, (c) subdomains per bucket. Option (a) is a two-line settings change + a one-shot object-move script. Migration is tiny (media bucket is post-Session-10-verification only; static is regenerated every `collectstatic`). |

### Route 53 record migration = state rm + `import` block

| Area | Decision |
|---|---|
| Choice | For each of the 4 Route 53 records (`apex_a`, `apex_aaaa`, `www_a`, `www_aaaa`): `terraform -chdir=infra/phase0 state rm 'aws_route53_record.<name>'`, then define the same resource in `infra/phase3/route53.tf` with a matching `import` block. Alias target updates from phase 0's CloudFront to phase 3's on the phase 3 apply. |
| Why | Move records **to** the module that owns their target. `state mv` doesn't cross state files. `state rm` in phase 0 leaves the records intact in AWS (they still resolve the whole time). `import` block in phase 3 attaches them to Terraform state atomically on `apply`. The apply then updates the alias target — Route 53 handles alias swaps within seconds and there's no TTL-based delay because aliases don't cache. Effective downtime: zero (or single-digit seconds). |

### `SECURE_SSL_REDIRECT` stays `False` (CloudFront enforces)

| Area | Decision |
|---|---|
| Choice | Set `viewer_protocol_policy = "redirect-to-https"` on every CloudFront behavior and leave `SECURE_SSL_REDIRECT = False` in Django. |
| Why | CloudFront is always in the request path; letting Django also issue a redirect creates a double-redirect risk (CloudFront redirects HTTP→HTTPS, Django then evaluates the request with `X-Forwarded-Proto: https` and is fine). If we ever bypass CloudFront (direct EIP hit for debugging), the site still responds without a redirect loop. |

### HSTS deferred to Session 15 hardening pass

| Area | Decision |
|---|---|
| Choice | Do NOT set `SECURE_HSTS_SECONDS` this session. |
| Why | HSTS with a real `max_age` is a one-way commitment — browsers pin the header for that duration and will refuse HTTP fallback. Prefer to let HTTPS soak for a session or two before making that commitment. Session 15 (or a dedicated hardening pass) will land `SECURE_HSTS_SECONDS = 60`, ramp to `31536000` after a week of stability, and enable `SECURE_HSTS_PRELOAD` + submit to hstspreload.org. |

### `CSRF_TRUSTED_ORIGINS` sourced from env, not derived from `DOMAIN`

| Area | Decision |
|---|---|
| Choice | Read `CSRF_TRUSTED_ORIGINS` from env as a comma-separated list (same shape as `ALLOWED_HOSTS`); fallback to `[f'https://{DOMAIN}', f'https://www.{DOMAIN}']` if unset. |
| Why | Symmetric with ALLOWED_HOSTS; makes it easy to add other origins (e.g., a staging subdomain) later without a redeploy. Fallback covers the local `manage.py runserver --settings=config.settings.production` path. |

### CloudFront cache policies + origin request policies (AWS-managed IDs)

| Area | Decision |
|---|---|
| Choice | S3 origins use managed **CachingOptimized** (`658327ea-f89d-4fab-a63d-7e88639e58f6`) + no origin request policy — S3 doesn't need extra headers. EC2 origin uses managed **CachingDisabled** (`4135ea2d-6df8-44a3-9df3-4b5a84be39ad`) + managed **AllViewer** origin request policy (`216adef6-5c7f-47e4-b989-5492eafa07d3`) so cookies + CSRF + user-agent + **Host header** all reach Django unchanged. |
| Why | Managed policies pin to well-known IDs, so plan diffs stay stable across releases. Forwarding the viewer's `Host` (apex or www) is what makes `request.build_absolute_uri()` produce correct absolute URLs — otherwise Django would build links back to `ec2-<eip>.compute-1.amazonaws.com`. ALLOWED_HOSTS already lists apex + www + EIP (the last one for direct debug hits), so `DisallowedHost` never fires. |

### No custom error page rewrite on the dynamic distribution

| Area | Decision |
|---|---|
| Choice | Do NOT set `custom_error_response` on the phase 3 distribution. Django's 404/500 pages pass through. |
| Why | The phase 0 distribution rewrote every error to a maintenance page — appropriate when the "site" was a single page. Phase 3 has real Django views, real 404s, real 500s; hiding them behind a rewrite would mask real bugs and make debugging harder. |

---

## Progress

- [x] Session log created (this file).
- [x] `infra/phase3/variables.tf` — added `acm_certificate_arn`, `hosted_zone_id`.
- [x] `infra/phase3/terraform.tfvars` — user added values (gitignored).
- [x] `infra/phase3/cloudfront.tf` written.
- [x] `infra/phase3/s3_media.tf` + `s3_static.tf` — bucket policies added.
- [x] `infra/phase3/outputs.tf` — CloudFront outputs.
- [x] `backend/config/settings/production.py` — proxy header, secure cookies, CSRF_TRUSTED_ORIGINS parsing, AWS_LOCATION on both storages.
- [x] `backend/config/tests.py` — 8 new tests (CSRF trusted origins ×3, secure/proxy ×3, storage location ×2).
- [x] `infra/phase3/ssm.tf` — `AWS_S3_CUSTOM_DOMAIN`, `AWS_STATIC_CUSTOM_DOMAIN`, `CSRF_TRUSTED_ORIGINS` params.
- [x] `infra/phase3/route53.tf` — 4 records + 4 `import` blocks.
- [x] `terraform validate` + `fmt -diff` + non-ASCII grep — clean (non-ASCII hits are in comments + Terraform output descriptions, not AWS resource descriptions).
- [x] Django test suite green — 55 tests, ok (47 baseline + 8 new).
- [x] User: `aws sso login`.
- [x] User: `terraform state rm` × 4 in phase 0.
- [x] User: `terraform plan` + `apply` in phase 3 — succeeded on the third attempt after two digressions (CNAMEAlreadyExists + phase 0's route53.tf still creating records; see below).
- [x] `curl -sI https://kaitlynandsteventietheknot.com` + `https://www.kaitlynandsteventietheknot.com` return 200; static assets return `x-cache: Hit from cloudfront` on second hit; `/admin/login/` sets `csrftoken` cookie with `Secure; SameSite=Lax`; Django 404 passes through cleanly.
- [x] Media object migration — not needed; media bucket had 0 objects at cutover.
- [x] User: `terraform destroy` in phase 0.
- [x] `infra/phase0/README.md` marked retired.
- [x] Branch protection instructions drafted; **UI configuration deferred to Session 15** (user out of time this session).
- [x] Session log finalized.

**End state:** `https://kaitlynandsteventietheknot.com` and
`https://www.kaitlynandsteventietheknot.com` serve the wedding site
through the phase 3 CloudFront distribution. HTTP requests 301 to
HTTPS at the edge. Static assets served under `/static/*` from the
static bucket with `location='static'`. Media pipeline ready under
`/media/*` (bucket empty at cutover). Phase 3 Terraform state at 55
resources; phase 0 state fully destroyed.

### Static bucket cleanup — deferred

Static bucket ended up with two copies of every asset:

- **343 objects under `static/`** (Session 14's collectstatic after the
  instance replace with `location='static'`).
- **343 objects at bucket root** (`admin/`, `css/`, `fonts/`, `frontend/`,
  `img/`, `js/`, and one root manifest file — from the instance's
  pre-Session-14 boot when `location` wasn't set).

The root-level objects are unreferenced (Django's manifest points at the
new hashed `static/*` names) and cost pennies to keep. A one-shot boto3
delete of everything not under `static/` was drafted this session but
deferred pending explicit user OK — leaving it as a follow-up rather
than acting on shared S3 state without confirmation.

## Digressions worth remembering

Three failure loops during the apply. Each landed as a fix in the
Session 14 files and taught us something about cross-module Terraform
migrations.

**1. `CNAMEAlreadyExists` on phase 3 CloudFront create.** Phase 0's
CloudFront distribution still owned `kaitlynandsteventietheknot.com`
and `www.kaitlynandsteventietheknot.com` as CNAMEs when phase 3 tried
to create its distribution with the same aliases. AWS refuses to let
two distributions claim the same alias.

Fix: two-step release-and-claim. Edit `infra/phase0/cloudfront.tf` to
set `aliases = []`, `terraform apply` phase 0 (~15 min for CF global
propagation), then rerun phase 3 apply. During the ~15-25 min window
between phase 0 releasing aliases and phase 3 claiming them, browser
hits to apex/www returned CF's `403 The request could not be
satisfied` — pre-launch, that's acceptable. **Lesson for future
CloudFront migrations:** the source distribution's aliases must be
released before the target can claim them. Plan for a downtime window
or a viable fallback path (e.g., temporary EIP direct DNS A-record).

**2. Phase 0's `route53.tf` still tried to create the R53 records.**
Session's plan said `terraform state rm` on the 4 records from phase 0,
which detaches them from state but leaves them in AWS. The `.tf`
resource definitions in `phase0/route53.tf` were still present, so
phase 0's next plan wanted to `+ create` them — and AWS rejected
with `InvalidChangeBatch: record set already exists`.

Fix: `rm infra/phase0/route53.tf` entirely. State rm removes the state
attachment; deleting the config removes Terraform's intent to manage.
**Lesson:** cross-module resource migration is a three-step dance —
(1) state rm from source, (2) delete source config, (3) import to
target. Skipping (2) means source module still tries to re-create.

**3. Django admin `is_staff` gotcha post-migrate.** User reset a
Django admin password via `manage.py shell` on a LOCAL environment
(SQLite), then tried to log in against the prod RDS-backed admin.
Password mismatch → "Please enter the correct username and password
for a staff account" error, which Django uses for both wrong
credentials and `is_staff=False`. Root cause was environment
confusion (local shell vs prod shell), not a Session 14 config bug.
Fix: `python manage.py createsuperuser` via SSM into the prod
instance so the shell hit RDS. **Lesson:** admin credentials do not
migrate with schema — they live in the database rows. Fresh prod DB
= fresh superuser needed. Worth adding to a Phase 5 launch checklist.

---

## Files created / modified this session

*(Filled in during execution.)*

**Created:**
- `.claude/sessions/2026-08-05-session-14-phase3-cloudfront-and-dns-cutover.md` — this log
- `infra/phase3/cloudfront.tf`
- `infra/phase3/route53.tf`

**Modified:**
- `infra/phase3/variables.tf`
- `infra/phase3/terraform.tfvars.example`
- `infra/phase3/outputs.tf`
- `infra/phase3/s3_media.tf`
- `infra/phase3/s3_static.tf`
- `infra/phase3/ssm.tf`
- `backend/config/settings/production.py`
- `backend/config/tests.py`
- `infra/phase0/README.md`

Per working contract, all `git add` / `git commit` is left to the user.

## Session 15 handoff

Session 15 = **branch protection setup (deferred from Session 14) +
CloudWatch Agent + log groups + retention + ERROR alarm + GitHub
Actions OIDC deploy role + `deploy.yml`.** Do the branch protection
step FIRST — it's a UI-only task the user ran out of time to execute
this session, and having it in place before landing the OIDC deploy
role is the whole point (deploy runs on `push` to `main`, and we want
main protected before that starts firing).

### Step 1 — branch protection on `main` (user, GitHub UI)

**Settings → Rules → Rulesets → New branch ruleset:**

- **Ruleset name:** `main-protected`
- **Enforcement status:** Active
- **Target branches:** Include default branch (`main` only)
- **Rules to enable:**
  - ☑ **Restrict deletions**
  - ☑ **Block force pushes**
  - ☑ **Require a pull request before merging**
    - Required approvals: `0` (solo project, but keeps the PR workflow)
    - ☑ Require conversation resolution before merging
  - ☑ **Require status checks to pass**
    - Select `python` and `frontend` (the two jobs in
      `.github/workflows/ci.yml`)
    - ☑ Require branches to be up to date before merging
- **Bypass list:** add `stnielse` as Role: Repository admin, Mode:
  Always. Emergency direct-push valve; every other push has to go
  through PR + CI.

After enabling: verify by trying to push a nonsense commit directly
to `main` from a feature branch checkout — should be rejected. Then
open a real PR and confirm the CI checks show up as "Required."

### Step 2 — CloudWatch Agent + log groups + retention

Carried from Session 12's handoff, unchanged. Ship gunicorn stderr +
nginx access/error + system journald to CloudWatch Logs. Every group
gets an explicit `retention_in_days` (project rule). One metric
filter + alarm for `ERROR` level records in `/wedding/django`.

### Step 3 — GitHub Actions OIDC deploy role + `deploy.yml`

Carried from Session 12's handoff, unchanged. IAM role assumable
only by the repo's OIDC identity; `deploy.yml` runs on `push` to
`main` (which now requires PR + CI per Step 1) and uses SSM
`send-command` to trigger a pull-and-restart on the EC2 box. Also a
good place to decide whether to keep building the frontend on the
instance (Session 13's default) or switch to CI-build-then-rsync.

### Step 4 — HSTS ramp

Add `SECURE_HSTS_SECONDS = 60` first, verify no breakage on both
HTTP-fallback paths (EIP debug hit, CloudFront cold start), ramp to
`31536000`. Optionally submit to hstspreload.org after two weeks of
stability. Also add `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` once the
long max_age is in.

### Step 5 — static bucket cleanup (from Session 14 deferred)

343 stale objects at bucket root in `wedding-site-static-<acct>`
(under `admin/`, `css/`, `fonts/`, `frontend/`, `img/`, `js/`, and
one root manifest). Session 14 drafted a boto3 delete-everything-not-
under-`static/` script but deferred pending user OK. Quick one-shot;
tack it onto Session 15's start if you like.

## Open questions / follow-ups

*(Carried from Session 13 unchanged unless noted.)*

- Q1 dietary + Q6 schedule — still open from Session 7.
- Photo alt-text values — final copy still pending.
- Deletion protection on RDS — flip closer to the wedding.
- `<picture>` mobile crop for hero — Session 15+.
- `django-vite` — still deferred.
- Real gallery page — Session 15+.
- Frontend build on EC2 vs CI-shipped artifacts — Session 15 (deploy
  workflow) may switch to CI-build-then-rsync.
- HSTS — see Session 15 handoff above.
