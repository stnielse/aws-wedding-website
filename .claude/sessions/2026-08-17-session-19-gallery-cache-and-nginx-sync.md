# Session 19 — CloudFront cache policy on /gallery/, nginx sync in deploy path

**Date:** 2026-08-17
**Mode:** Execution — infra + deploy workflow
**Model:** Opus 4.7

---

## Context

Two items from Session 18's handoff, batched into one session:

1. **CloudFront cache policy on `/gallery/`.** Currently every HTML page
   load is `CachingDisabled` (`4135ea2d-…`), so `/gallery/` hits
   EC2 → gunicorn → Django → RDS on every request. Gallery view
   serializes 324 Photo rows into a 342 KB HTML payload with an
   inline JSON island — non-trivial ORM + template work per request.
   If the wedding link gets shared and 500–5000 relatives hit
   `/gallery/` in a day, EC2 CPU credits could saturate on the
   `t3.micro` + `db.t3.micro` pair — not a cash-cost issue (both
   flat-rate) but a throttling/latency issue for real viewers.
2. **Extend `scripts/deploy.sh` to sync nginx config to the live box.**
   S18 digression 2 flagged the workflow gap: `nginx-site.conf.tftpl`
   is rendered into `user_data` by TF, but `user_data_replace_on_change = false`
   means TF `apply` never touches the running nginx config. Every
   nginx template change today requires a manual on-box SSM apply
   (S18 did this by hand). Folding nginx sync into the deploy path
   closes the gap: any push-to-main whose diff touches the template
   picks up automatically.

### Skipped from S18's handoff (still not due)
- **HSTS ramp** — earliest 2026-08-19 (2 days out); gated on ERROR/CRITICAL
  filter staying quiet. Not this session.
- **RDS deletion protection** — 2027-01/02 calendar item.
- **Photo alt-text / captions** — admin follow-up, not workflow-blocking.
- **Auto-invalidation on Photo save** — deferred to S20 (see decisions below).

---

## Decisions locked this session

### Gallery cache policy — 5-min default, 15-min max, `/gallery*` path pattern, no cookies/qs in cache key

| Area | Decision |
|---|---|
| Choice | New `aws_cloudfront_cache_policy.gallery`: `min_ttl=60`, `default_ttl=300`, `max_ttl=900`. Cookies `none`, query strings `none`, headers `none`, `enable_accept_encoding_brotli = true`, `enable_accept_encoding_gzip = true`. New `ordered_cache_behavior` with `path_pattern = "/gallery*"` targeting `ec2-web` origin, `allowed_methods = ["GET","HEAD","OPTIONS"]`, keeps `AllViewer` origin request policy (216adef6-…) so `Host` still forwards to Django for `build_absolute_uri`. |
| Why | **Why HTML caching is safe here.** `/gallery/` is a read-only view of the Photo queryset — no per-guest personalization, no CSRF-bearing form on the page, no auth-gated content. All viewers see the same HTML. So a shared CloudFront cache is functionally correct. **Why 5-min TTL not 1-hour.** Admin adds/edits of photos should propagate quickly enough that a photographer or the wedding party doesn't have to explain "reload in an hour." 5 minutes is short enough to feel near-live during active admin work, long enough to absorb a 5000-hit spike into ~15 origin requests (5000 hits / (300s * 1 req/300s)). **Why no auto-invalidation this session.** Would require IAM permission add (`cloudfront:CreateInvalidation`), an SSM param plumbing the distribution ID into Django, a `post_save`/`post_delete` signal on Photo, and its own tests. 15-min worst-case staleness is fine for admin adds — we can layer invalidation in later if the wedding link goes wide and admin edits during peak traffic become common. Deferred to S20. **Why `/gallery*` not `/gallery/*`.** `*` matches zero-or-more chars, and CloudFront path-pattern semantics for `/gallery/*` vs `/gallery/` are subtle in the trailing-slash boundary case. `/gallery*` unambiguously matches `/gallery`, `/gallery/`, and `/gallery/<anything>` — cleaner and there is no other `/gallery`-prefixed route to conflict with (Django's admin lives at `/admin/*`). **Why AllViewer origin request policy stays.** Cache-key config (in the cache policy) decides what varies per cache entry — none here. Origin request policy decides what gets forwarded to the origin per uncached fetch. Django needs `Host` forwarded so `build_absolute_uri` produces apex URLs, not the CloudFront-internal hostname. AllViewer forwards everything, none of which is cache-key material after this change. **Why brotli+gzip in cache key.** A viewer that supports brotli should get the brotli-encoded response; one that only supports gzip should get gzip. Two cache entries per URL (br vs gz) is fine. **Cost sanity.** CloudFront request pricing is $0.0075/10K in the US, so even 100K `/gallery/` hits/mo is <$0.10. Data transfer out is unchanged (image bytes still flow through the /media/* behavior). |

### `/schedule/`, `/travel/`, other cacheable pages — deferred, not batched into this policy

| Area | Decision |
|---|---|
| Choice | Only `/gallery*` gets a cache behavior this session. `/schedule/`, `/travel/`, other Django-rendered static-ish pages stay on the default `CachingDisabled` behavior for now. |
| Why | Same cache policy resource is reusable — future sessions can add more `ordered_cache_behavior` blocks pointing at the same policy without churn. Scoping this session to `/gallery/` keeps the plan diff small (one cache policy, one behavior) and matches the reason we're doing this at all: gallery is the fat, viral-risk page. `/rsvp/` must stay `CachingDisabled` because per-guest CSRF cookies + form state make caching unsafe; `/admin/*` obviously stays `CachingDisabled`. |

### Nginx sync in deploy — repo-shipped helper script + narrow sudoers grant, driven from `scripts/deploy.sh`

| Area | Decision |
|---|---|
| Choice | New `scripts/wedding-nginx-sync.sh` in the repo: backs up current `/etc/nginx/conf.d/wedding-site.conf` to `.bak`, copies `/tmp/wedding-site.conf.new` into place, runs `nginx -t`, rolls back on failure, otherwise `systemctl reload nginx`. `scripts/deploy.sh` renders the template via `envsubst '${domain_name}'` (whitelist so `$host`, `$request_uri`, `$scheme` — nginx runtime vars — stay literal), writes to `/tmp/wedding-site.conf.new`, `cmp -s` against the live file, and invokes `sudo /home/ec2-user/aws-wedding-website/scripts/wedding-nginx-sync.sh` only on change. Sudoers entry (`/etc/sudoers.d/wedding-site-deploy`, managed in `user_data.sh.tftpl`) grows to NOPASSWD both the existing `systemctl restart gunicorn` AND the new sync script by exact path. |
| Why | **Why a repo-shipped helper script, not inline in deploy.sh.** The privileged operations (write to `/etc/nginx/conf.d/`, `nginx -t`, `systemctl reload nginx`) are the sudoers-scoped surface. If sudoers grants NOPASSWD to a fixed script path, we can iterate on the *implementation* of the sync without touching sudoers — every deploy pulls the latest script via `git checkout`. Alternative — three separate sudoers lines for `cp`, `nginx -t`, `systemctl reload nginx` — works but sprawls sudoers, and inline deploy.sh handling would mean re-editing sudoers if the sequence changes. Single-script grant is the cleanest scope-narrowing. **Why an exact path under ec2-user's home for the sudoers target.** ec2-user is the user we're granting sudo to; if that account is compromised, sudoers scope-narrowing is not the last line of defense. The narrowing here is against *accidental* sudo (typo in deploy.sh), which the path pin catches perfectly. **Why `cmp -s` first, no-op if unchanged.** Every deploy exercises this code path; most deploys don't touch nginx. `nginx -t` + `systemctl reload nginx` on every deploy would be noise (systemd log entries, brief nginx worker recycle). Diff-and-skip keeps quiet deploys quiet. **Why `envsubst '${domain_name}'` with an explicit whitelist.** The template mixes Terraform interpolation (`${domain_name}`) with nginx runtime variables (`$host`, `$request_uri`, `$scheme`). Bare `envsubst` would clobber the nginx vars (treat `$host` as empty shell var). The whitelist form substitutes only listed vars, leaving the rest literal. Same shape as Terraform's own `templatefile()` — only `${domain_name}` gets expanded, everything else is passed through. **Why rollback in the helper, not just `set -e` in deploy.sh.** S18 digression 1's failure mode: config on disk is broken, but nginx is running in-memory with the old config — site stays up until the next unrelated reload, then dies. Explicit backup + validate + rollback ensures the on-disk state matches the running state after the sync completes, success or failure. **Why not close the gap with a Terraform `null_resource` + SSM trigger instead.** S18 discussion covered this: any change flow that requires `terraform apply` to reach the live box splits the "deploy" mental model into "code deploy (CI)" vs "infra deploy (terraform apply)". Folding into the CI deploy path keeps a single source of truth for "how does a change reach the live box." The template still lives in `infra/phase3/templates/` because that's where user_data reads it for fresh instances — both paths render from the same source. |

### Current-instance one-time apply — sudoers patch via SSM send-command with `jq` JSON payload

| Area | Decision |
|---|---|
| Choice | The sudoers change added to `user_data.sh.tftpl` this session takes effect on future instance rebuilds only (same `user_data_replace_on_change = false` reason). A one-time SSM send-command patches `/etc/sudoers.d/wedding-site-deploy` on the current live box to add the sync-script NOPASSWD line. Payload built with `jq -n --arg cmd … '{commands:[$cmd]}'` per the CLAUDE.md SSM rule. Full command recipe in the [Applying user_data-templated changes to the current live instance](#applying-user_data-templated-changes-to-the-current-live-instance) section. |
| Why | Standard S17/S18 pattern — `user_data` fires only on first boot, so any change to the sudoers file baked into user_data doesn't reach a live instance. `visudo -c -f` in the patch script catches syntax errors before the file is trusted by sudo. Idempotent: patch script checks whether the new line is already present before appending. |

---

## Progress

- [x] Session log created (this file).
- [x] `infra/phase3/cloudfront.tf` — add `aws_cloudfront_cache_policy.gallery` + `ordered_cache_behavior` for `/gallery*`.
- [x] `scripts/wedding-nginx-sync.sh` — new helper: backup + cp + validate + rollback + reload. Chmod +x.
- [x] `scripts/deploy.sh` — nginx sync step inserted between Python deps and frontend tar extract; sources `.env` for `$DOMAIN`, uses `envsubst '${domain_name}'` whitelist, `cmp -s` diffs, sudo-invokes the helper only on change.
- [x] `infra/phase3/templates/user_data.sh.tftpl` — sudoers entry extended with the helper path; `gettext` added to the `dnf install` list so `envsubst` is present on future rebuilds (current box may need it installed if missing — see below).
- [x] Local pre-plan checks: `terraform validate` passes; `terraform fmt -check cloudfront.tf` clean; `bash -n` clean on both shell files; `envsubst` rendering verified to substitute `${domain_name}` only and preserve `$host`/`$request_uri`/`$scheme` literally; Django tests 67/67 still passing.
- [x] `terraform plan` reviewed with user — hit two issues on first plan; both fixed. See [Digressions](#digressions-worth-remembering) below. Re-plan expected diff: one new resource (`aws_cloudfront_cache_policy.gallery`), one in-place update to `aws_cloudfront_distribution.web` (single new `ordered_cache_behavior` appended after `/static/*`), one in-place update to `aws_instance.web` user_data (now `user_data_base64`, computed content, no replace since `user_data_replace_on_change = false`). S3 bucket policy diffs from the first plan should no longer appear.
- [ ] `terraform apply tfplan` run.
- [x] Post-apply: one-time SSM patch of `/etc/sudoers.d/wedding-site-deploy` applied to the live box; `visudo -c` accepted the new file; `envsubst` confirmed present at `/usr/bin/envsubst`. Verification via `sudo -l -U ec2-user` surfaced an unrelated finding — see [Digression 3](#digressions-worth-remembering) — but does not block S19.
- [x] Post-apply verification (partial, sufficient for session close): `curl -sI https://kaitlynandsteventietheknot.com/gallery/` twice ~3 s apart showed the `age` header incrementing by 3 (`age: 0` → `age: 3`), proving the `/gallery*` cache behavior is live at CloudFront and the entry is being served from edge cache. Full deploy-path verification (no-op sync on first deploy, then a trivial template edit to prove sync-on-change) is deferred to the CI push flow — user will merge the PR through the normal main-gate, with an emergency direct-to-main push as fallback if the deploy fails on the new nginx sync step.
- [x] Session log finalized.

**On unit tests:** No application code shipped this session — changes are Terraform (`cloudfront.tf`), shell (`deploy.sh`, new `wedding-nginx-sync.sh`), and the sudoers line in `user_data.sh.tftpl`. Verification is `terraform validate` + `terraform plan` review + post-apply smoke tests (CloudFront `age` header check, deploy dry-run showing no-op path, deploy path showing sync-on-change). Django test suite still passes at 67/67 from S17 with no changes needed.

## Applying user_data-templated changes to the current live instance

Same shape as S18. The sudoers change baked into `user_data.sh.tftpl`
takes effect on future rebuilds; the current live t3.micro needs a
one-time patch. All commands run against the instance ID from TF output.

```
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)

BOX_CMD='set -e
SUDOERS=/etc/sudoers.d/wedding-site-deploy
LINE="ec2-user ALL=(root) NOPASSWD: /bin/systemctl restart gunicorn, /home/ec2-user/aws-wedding-website/scripts/wedding-nginx-sync.sh"
if ! grep -qF "wedding-nginx-sync.sh" "$SUDOERS"; then
    echo "$LINE" > "$SUDOERS.new"
    chmod 0440 "$SUDOERS.new"
    visudo -c -f "$SUDOERS.new"
    mv "$SUDOERS.new" "$SUDOERS"
    echo "sudoers patched"
else
    echo "sudoers already has wedding-nginx-sync entry; no-op"
fi
cat "$SUDOERS"'
PARAMS=$(jq -n --arg cmd "$BOX_CMD" '{commands: [$cmd]}')

command_id=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "S19 sudoers patch for nginx sync" \
    --parameters "$PARAMS" \
    --query 'Command.CommandId' --output text)
echo "Dispatched: $command_id"

aws ssm wait command-executed --command-id "$command_id" --instance-id "$INSTANCE_ID"
aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
  --output json \
  | jq -r '"status: \(.Status)", "----- stdout -----", .StandardOutputContent, "----- stderr -----", .StandardErrorContent'
```

`visudo -c -f` on the new file before `mv` catches syntax errors
before the live sudoers gets clobbered. `grep -qF wedding-nginx-sync.sh`
makes re-runs safe.

Once the sudoers patch is in, the next `git push` to `main` exercises
the new deploy.sh code path automatically. On the first push after
this session, `scripts/wedding-nginx-sync.sh` also needs to exist in
the repo on the box (it will, via `git checkout` in deploy.sh, since
the file is in this commit).

## Verification

**Cache policy live check:**
```
# First request: expect no `x-cache: Hit from cloudfront`, `age: 0` or absent
curl -sI https://kaitlynandsteventietheknot.com/gallery/ | grep -Ei '^(age|x-cache|cache-control|content-length):'

# Wait a few seconds, hit again from a fresh curl invocation
curl -sI https://kaitlynandsteventietheknot.com/gallery/ | grep -Ei '^(age|x-cache|cache-control|content-length):'
```
Second hit should show `x-cache: Hit from cloudfront` (or `RefreshHit`)
and a nonzero `age` header. Content-length should match between requests.

**Deploy dry-run (post-sudoers-patch, before pushing the template edit):**
The next deploy exercises the sync step but finds the config unchanged
and no-ops. Watch for the log line `nginx config unchanged; skipping sync`
in the SSM invocation output.

**Deploy sync-on-change:** Make a trivial no-op edit to
`nginx-site.conf.tftpl` (add a whitespace-only comment), push, watch
the deploy log emit `nginx config changed; syncing` followed by the
helper script's success output, then confirm `curl -I https://...`
still returns `HTTP/2 200`.

## Files created / modified this session

**Created (planned):**
- `.claude/sessions/2026-08-17-session-19-gallery-cache-and-nginx-sync.md` — this log.
- `scripts/wedding-nginx-sync.sh` — helper script called from deploy.sh via sudo.

**Modified (planned):**
- `infra/phase3/cloudfront.tf` — new `aws_cloudfront_cache_policy.gallery` resource + `ordered_cache_behavior` block for `/gallery*`.
- `scripts/deploy.sh` — new nginx sync step between Python deps and Django migrate.
- `infra/phase3/templates/user_data.sh.tftpl` — sudoers entry grows to include the new helper path.

Per working contract, all `git add` / `git commit` / `git push` is left
to the user. Recommended commit message:

    Session 19 — CloudFront /gallery/ cache policy, nginx sync in deploy path

## Digressions worth remembering

**1. `aws_instance.user_data` hard-limits at 16 KB; adding one sudoers line + one dnf package tipped the wedding-site bootstrap over.**

First `terraform plan` for this session failed with:
```
Error: expected length of user_data to be in the range (0 - 16384), got #!/bin/bash…
```
The AL2023 bootstrap in `user_data.sh.tftpl` had been sitting comfortably around ~14 KB since Session 15. Session 18 (swap block) pushed it up a bit, and Session 19's additions (`gettext` in the dnf list, one more path in the sudoers grant, extended sudoers comment) tipped it past 16,384 bytes.

**Fix:** switched `aws_instance.web` from `user_data = templatefile(...)` to `user_data_base64 = base64gzip(templatefile(...))`. cloud-init on AL2023 detects gzip magic bytes at the start of user_data and decompresses transparently before executing — no on-box change needed. Base64 wrapping is required because `user_data_base64` expects an already-encoded string. gzip + base64 packed the ~15 KB rendered script to ~6-7 KB, giving comfortable headroom for future additions.

**Guidance:** future user_data edits should keep an eye on the compressed size (approximate: `wc -c` on the raw template + inline `nginx-main.conf.tftpl`/`nginx-site.conf.tftpl`/`gunicorn.service.tftpl` contents, then `| gzip | base64 | wc -c` for the encoded footprint). If it ever crosses ~12 KB compressed, start factoring cold-content (systemd unit, nginx configs) out to SSM parameters and fetching them at boot instead of baking them into user_data.

**2. `ordered_cache_behavior` is a positional list, not a set — inserting a new block at position 0 shuffles every downstream block into a "changed" diff.**

First plan showed `ordered_cache_behavior` diffs like:
```
~ ordered_cache_behavior {
    ~ path_pattern     = "/media/*" -> "/gallery*"
    ~ target_origin_id = "s3-media" -> "ec2-web"
    ...
```
Not what actually would happen at CloudFront — the resulting live distribution would still have `/media/*`, `/static/*`, `/gallery*` behaviors — but Terraform tracks them by list index and re-diffs each position when the list grows. Worse, the reshuffle made `cache_policy_id` at position 0 reference `aws_cloudfront_cache_policy.gallery.id` (a resource being created), which cascaded to the distribution's `arn` being `(known after apply)`, which forced both `aws_s3_bucket_policy.media` and `aws_s3_bucket_policy.static` into `(known after apply)` diffs too.

**Fix:** moved the new `/gallery*` block to the END of the ordered_cache_behavior list (after `/media/*` and `/static/*`). Existing blocks stay byte-identical, only position 2 is new. S3 bucket policy diffs should disappear on the re-plan. Path patterns don't overlap, so evaluation-order change is functionally a no-op at CloudFront.

**Guidance:** append new ordered_cache_behavior blocks unless there's a semantic reason to insert them earlier (path pattern overlap with an existing block — first match wins in CloudFront's evaluation). Adding "logically first" is a Terraform-diff hazard, not a CloudFront correctness win.

**3. ec2-user has global `(ALL) NOPASSWD: ALL` via cloud-init's default `/etc/sudoers.d/90-cloud-init-users` — our narrow NOPASSWD grants are decorative.**

Surfaced during the S19 sudoers verification. `sudo -l -U ec2-user` on the box:
```
User ec2-user may run the following commands on ip-10-0-1-77:
    (ALL) ALL
    (ALL) NOPASSWD: ALL
    (root) NOPASSWD: /bin/systemctl restart gunicorn, /home/ec2-user/aws-wedding-website/scripts/wedding-nginx-sync.sh
```

The first `(ALL) NOPASSWD: ALL` grant comes from `/etc/sudoers.d/90-cloud-init-users` (128 bytes, present on every AL2023 EC2 instance out of the box). It grants ec2-user passwordless sudo to everything, which is what has actually been letting `scripts/deploy.sh` run `sudo /bin/systemctl restart gunicorn` for the past four sessions — the narrow `wedding-site-deploy` sudoers file we've been carefully maintaining has been redundant the whole time. Also explains why the S19 patch found the file missing without any deploy having failed: the global grant was covering.

**Security posture implication:** the least-privilege intent of the narrow entries is defeated. Anything that lands as ec2-user (via SSM SendCommand, a compromised deploy script, or any RCE in the Django app that escalates to the app-user shell) can `sudo` anything. Removing cloud-init's grant is a real hardening lever but has to be done carefully — SSM Session Manager access should stay usable, and any admin recovery paths that depend on `sudo -i` need alternatives lined up first. Not in scope for S19. Added to open questions as an S20+ security-hardening candidate.

## Open questions / follow-ups

*(Carried from S18 unless noted; new items marked NEW.)*

- **NEW — Remove or narrow cloud-init's `(ALL) NOPASSWD: ALL` grant to
  ec2-user (`/etc/sudoers.d/90-cloud-init-users`).** Surfaced during
  the S19 sudoers verification (Digression 3). Current global grant
  makes every narrow NOPASSWD entry in `wedding-site-deploy`
  decorative. Real hardening lever but has to be done carefully to
  avoid breaking SSM Session Manager admin access. Terraform can drop
  a replacement `/etc/sudoers.d/00-cloud-init-users` in user_data
  (higher precedence via lower number) that grants ec2-user only what
  SSM + our narrow entries need. Own session — nontrivial rollback plan.
- **NEW — Auto-invalidation on Photo save/delete.** Deferred from
  this session. If wedding link goes viral and admin edits during
  peak traffic become common, add a `post_save`/`post_delete` signal
  on Photo that calls `boto3.client('cloudfront').create_invalidation(
  DistributionId=<from SSM>, Paths=['/gallery*'])`. Requires: (a)
  new IAM policy grant on the EC2 role for `cloudfront:CreateInvalidation`
  scoped to the distribution ARN, (b) new SSM param
  `CLOUDFRONT_DISTRIBUTION_ID` (plumb into `.env`), (c) Django
  settings + signal wiring, (d) tests. Small session on its own.
- **NEW — Extend cache policy to other read-mostly Django pages.**
  Same `aws_cloudfront_cache_policy.gallery` resource is reusable —
  add ordered_cache_behavior blocks for `/schedule/`, `/travel/`,
  etc. as they land. `/rsvp/` and `/admin/*` must stay `CachingDisabled`.
- **HSTS ramp** — earliest 2026-08-19, gated on ERROR/CRITICAL log filter staying quiet.
- **RDS deletion protection** — flip 2027-01/02.
- **Photo alt-text / captions** — bulk sync leaves both blank; add via admin as time allows.
- **`<picture>` mobile crop for hero** — carried from S15.
- **`django-vite`** — deferred, not blocking.
- **Q1 dietary + Q6 schedule** — open from Session 7 (RSVP).
