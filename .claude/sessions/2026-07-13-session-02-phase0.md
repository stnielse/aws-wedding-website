# Session 02 — Phase 0 Maintenance Page

**Date:** 2026-07-13
**Mode:** Implementation — Terraform module + static HTML
**Model:** Opus 4.7

---

## Context

Session 1 (`2026-07-13-session-01-design.md`) locked scope and working-contract
rules. This session ships **Phase 0** from the handoff build order: the domain
must resolve to a tasteful "under construction" page, served over HTTPS, backed
by infrastructure that `terraform destroy` will clean up without residue.

Foundational AWS state already in place (from `pre-claude-setup.md`):

- Route 53 hosted zone for the wedding domain (created via Route 53 domain
  registration).
- ACM certificate for the domain (and `www` SAN, expected) issued in
  `us-east-1`, DNS-validated.
- IAM admin user, budget, cost anomaly detection.

Nothing has been provisioned via Terraform yet — this module is the first.

---

## Decisions locked this session

| Area | Decision |
|---|---|
| Phase 0 hosting | **S3 + CloudFront + Route 53 alias.** Private bucket (OAC), single CloudFront distribution attached to the existing ACM cert, custom 403/404 error responses map to `/index.html` with a 200 so every path serves the maintenance page. |
| Phase 0 IaC | **Terraform module at `infra/phase0/`.** No console click-through — every resource is code so teardown is a single `terraform destroy`. |
| Terraform state backend | **Local state** for `infra/phase0/`. State file lives beside the module (gitignored). The S3+DynamoDB backend the handoff describes is for the main `infra/` config in Phase 3 — introducing it now would add two more resources we'd have to manage before we need them. |
| Maintenance copy | **Minimal placeholder.** No names, no date, no venue — the page is publicly reachable before the site-access code lands in Phase 2, so it must not leak invite details. |
| Bucket `force_destroy` | `true`. The bucket only holds the maintenance HTML; teardown must not require manual object cleanup. |
| Distribution reuse plan | The Phase 0 distribution is **not** intended to be extended in-place into the Phase 4 distribution. Session 1 floated reusing it, but folding EC2 as a second origin later while keeping the maintenance-mode error responses would leave landmines (error responses masking real 404s). Cleaner: `terraform destroy` this module when Phase 3 starts, then create the production distribution fresh in `infra/cloudfront.tf`. |
| Deferred decisions | Site-access-code storage and photo intake workflow — both are Phase 2+ concerns and don't gate Phase 0. Revisit when Phase 2 starts. |
| Version pin style | **Strict pins** on both the Terraform CLI (`1.15.8`) and the AWS provider (`6.54.0`) — user preference for exact versions over pessimistic constraints (`~>`) or floors (`>=`). Verified against the AWS provider 6.0 upgrade guide that none of the resources in this module (S3 bucket/policy/PAB/object, CloudFront distribution + OAC, Route 53 records, IAM policy document data source) have breaking changes touching our code. |

---

## Module design

Module lives at `infra/phase0/` and contains:

- `main.tf` — Terraform version + AWS provider (region `us-east-1` since CloudFront cert lives there).
- `variables.tf` — `domain_name`, `acm_certificate_arn`, `hosted_zone_id`, `project_tag`.
- `s3.tf` — private bucket with public-access-block, OAC-restricted bucket policy, `aws_s3_object` for `index.html`.
- `cloudfront.tf` — distribution, OAC, custom error responses for 403/404, HTTPS-only, HTTP→HTTPS redirect, price class 100 (NA + EU only).
- `route53.tf` — A alias records at apex and `www` pointing at the distribution.
- `outputs.tf` — `cloudfront_domain_name`, `cloudfront_distribution_id`, `bucket_name`.
- `terraform.tfvars.example` — committed placeholder values.
- `maintenance/index.html` — the static page.
- `README.md` — apply/verify/destroy runbook.

### Why these specific choices

- **OAC (Origin Access Control) not OAI** — OAI is legacy; OAC uses SigV4 and is the current AWS recommendation.
- **Custom error responses 403 & 404 → `/index.html` with 200** — S3 returns 403 for keys the caller can't see and 404 for missing keys; mapping both to a 200 on `index.html` means any path (`/`, `/rsvp`, `/whatever`) shows the maintenance page.
- **`price_class = PriceClass_100`** — NA + EU edge locations only; cheapest tier that still terminates TLS at the edge and is regionally appropriate for a US-based wedding.
- **`viewer_protocol_policy = redirect-to-https`** — HTTP redirected to HTTPS at the edge.
- **`force_destroy = true` on the bucket** — required for `terraform destroy` to remove the bucket without a manual `aws s3 rm` pass.
- **CloudWatch logging** — deliberately not enabled. No log group means no `retention_in_days` to forget, and no ongoing storage charge for a page that shouldn't get traffic anyway.
- **`.gitignore` broadening** — the existing patterns are `infra/*.tfstate` and `infra/*.tfvars` (top-level only). Since state and tfvars now live at `infra/phase0/`, patterns get broadened to `infra/**/*.tfstate` and `infra/**/*.tfvars`.

---

## Verification (to run after apply)

- `curl -I https://<domain>` → `200`, `via:` header mentions CloudFront.
- `curl -I http://<domain>` → `301` to `https://`.
- `curl -I https://www.<domain>` → `200`.
- `curl -I https://<domain>/nonexistent-path` → `200` (custom error response served the maintenance page).
- `curl -sI https://<bucket>.s3.amazonaws.com/index.html` → `403` (bucket is not directly public).
- Browser check: apex and `www` both render the page; page is legible on mobile.
- `terraform destroy` in a scratch run: exits clean, `aws s3 ls` shows the bucket gone, Route 53 records gone, distribution disabled + deleted (this step is slow — CloudFront disable → delete takes 15–30 min).

---

## Progress

- ✅ Confirmed Phase 0 scope with user (hosting = A, state = local, copy = minimal).
- ✅ Session log created.
- ✅ `.gitignore` broadened for `infra/**/` subdirs.
- ✅ `infra/phase0/` Terraform module written.
- ✅ `maintenance/index.html` written.
- ✅ `infra/phase0/README.md` written.
- ✅ Terraform CLI + AWS provider strict-pinned in `main.tf` after user chose 1.15.8 locally and registry showed 6.54.0 current.
- ✅ Walked user through Terraform concepts and the module file-by-file (user is new to TF).
- ⏭ **Not this session:** `terraform init/plan/apply` — user is still installing Xcode CLT + Terraform. Verification happens in Session 3.

## Files created / modified this session

- `.claude/sessions/2026-07-13-session-02-phase0.md` — this file
- `.gitignore` — broadened Terraform patterns from `infra/*` to `infra/**/*`
- `infra/phase0/main.tf` — provider config + strict version pins
- `infra/phase0/variables.tf` — 4 input variables (domain, ACM ARN, HZ ID, project tag)
- `infra/phase0/s3.tf` — bucket, ownership controls, public-access block, OAC bucket policy, `index.html` object
- `infra/phase0/cloudfront.tf` — OAC + distribution with ACM cert, 403/404 custom error responses → 200 on `/index.html`
- `infra/phase0/route53.tf` — A + AAAA alias records for apex and www
- `infra/phase0/outputs.tf` — bucket name, distribution ID, distribution domain name
- `infra/phase0/terraform.tfvars.example` — committed placeholder
- `infra/phase0/maintenance/index.html` — self-contained static page (dark-mode-aware, no external assets)
- `infra/phase0/README.md` — apply/verify/destroy runbook

Not yet committed. Per working contract, user runs `git add` / `git commit` themselves.

## Session 3 handoff

**Goal:** get the maintenance page live.

Prereqs the user needs to complete before Session 3 opens:

1. Xcode CLT + `hashicorp/tap` Terraform installed (in progress).
2. AWS CLI configured with the IAM admin user profile (`aws sts get-caller-identity` should return the admin user ARN, not root).
3. Look up + capture (into `terraform.tfvars`):
   - Apex domain name (Route 53 hosted zones page).
   - ACM certificate ARN — must be in us-east-1, status Issued, covering apex + `www` SAN.
   - Route 53 hosted zone ID for the apex domain.

Session 3 flow:

1. `cd infra/phase0 && cp terraform.tfvars.example terraform.tfvars` — user edits with real values.
2. `terraform init` — installs provider 6.54.0, writes `.terraform.lock.hcl` (this file **is** committed; state and tfvars are not).
3. `terraform plan` — walk through the plan output together; expect ~10 resources.
4. `terraform apply` — blocks 10-20 min on CloudFront deployment.
5. Run the verification block from `infra/phase0/README.md`.
6. Session 3 also runs the **teardown drill** the Session 1 log called out: apply → verify → `terraform destroy` → confirm the account has no residue. Then apply again to leave the maintenance page live. This validates the teardown discipline before we accumulate more infra.

Suggested session 3 slug: `2026-07-14-session-03-phase0-apply.md` (or whatever date it lands on).

**Deferred to a later session:**

- Building `cost-guard` and `wedding-copy-editor` subagents (Session 1 committed to both). Not needed until we start iterating on infra diffs, which won't happen until Phase 3.
- Site-access-code storage (Django setting vs `SiteAccessCode` singleton) — Phase 2.
- Photo intake workflow (admin upload vs `manage.py import_photos`) — Phase 2.
- Rewriting the handoff's EC2 setup snippet from apt/ubuntu to dnf/ec2-user — Phase 4.
