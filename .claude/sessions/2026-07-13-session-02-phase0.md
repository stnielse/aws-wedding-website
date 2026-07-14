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
- ⏳ Session log created.
- ⏳ `.gitignore` broadened for `infra/**/` subdirs.
- ⏳ `infra/phase0/` Terraform module written.
- ⏳ `maintenance/index.html` written.
- ⏳ `infra/phase0/README.md` written.

## Files created / modified this session

_(populated on session close)_

## Session 3 handoff

_(populated on session close)_
