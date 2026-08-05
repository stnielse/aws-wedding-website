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
- [ ] `infra/phase3/variables.tf` — add `acm_certificate_arn`, `hosted_zone_id`.
- [ ] `infra/phase3/terraform.tfvars` — add values (user does; gitignored).
- [ ] `infra/phase3/cloudfront.tf` written.
- [ ] `infra/phase3/s3_media.tf` + `s3_static.tf` — bucket policies added.
- [ ] `infra/phase3/outputs.tf` — CloudFront outputs.
- [ ] `backend/config/settings/production.py` — proxy header, secure cookies, CSRF_TRUSTED_ORIGINS parsing, AWS_LOCATION on both storages.
- [ ] `backend/config/tests.py` — new tests for CSRF + storage location.
- [ ] `infra/phase3/ssm.tf` — `AWS_S3_CUSTOM_DOMAIN`, `AWS_STATIC_CUSTOM_DOMAIN`, `CSRF_TRUSTED_ORIGINS` params.
- [ ] `infra/phase3/route53.tf` — 4 records + 4 `import` blocks.
- [ ] `terraform validate` + `fmt -diff` + non-ASCII grep — clean.
- [ ] Django test suite green (≥47 → ≥50).
- [ ] User: `aws sso login`.
- [ ] User: `terraform state rm` × 4 in phase 0.
- [ ] User: `terraform plan` + `apply` in phase 3.
- [ ] `curl -sI https://<apex>` + `https://www.<apex>` returns 200.
- [ ] Media object migration to `media/` prefix (if any objects exist).
- [ ] User: `terraform destroy` in phase 0.
- [ ] `infra/phase0/README.md` marked retired.
- [ ] Branch protection instructions handed to user.
- [ ] Session log finalized.

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

Session 15 = **CloudWatch Agent + log groups + retention + ERROR
alarm + GitHub Actions OIDC deploy role + `deploy.yml`.** Prep list
carried from Session 12's handoff, unchanged. Plus one new item:

- **HSTS ramp** — add `SECURE_HSTS_SECONDS = 60` first, verify no
  breakage on both HTTP-fallback paths (EIP debug hit, CloudFront
  cold start), ramp to `31536000`. Optionally submit to
  hstspreload.org after two weeks of stability.

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
