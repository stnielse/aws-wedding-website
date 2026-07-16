# Session 03 — Phase 0 Apply

**Date:** 2026-07-15
**Mode:** Execution — first `terraform apply` on this project
**Model:** Opus 4.7

---

## Context

Session 2 (`2026-07-13-session-02-phase0.md`) wrote the `infra/phase0/` module
and `maintenance/index.html` but stopped before `terraform init/plan/apply`
while the user finished installing tooling. This session runs the module end
to end: init → plan → apply → verify → teardown drill → re-apply, leaving the
maintenance page live at the apex + `www` over HTTPS.

Prereqs confirmed at session start:

- Terraform `1.15.8` on PATH (matches strict pin in `infra/phase0/main.tf`).
- AWS CLI installed via Homebrew (`brew install awscli`).
- User authenticates each session via `aws` login rather than a persisted
  `~/.aws/config` profile — session-scoped credentials, no long-lived keys
  in the shell profile.
- `aws sts get-caller-identity` returns the IAM admin user ARN, not root.
- `infra/phase0/terraform.tfvars` created and populated by the user with
  real values for domain, ACM ARN, hosted zone ID, project tag.

---

## Session plan

1. **init** — installs AWS provider `6.54.0`, writes `.terraform.lock.hcl`.
   Lock file **is** committed; `.terraform/`, state, and `terraform.tfvars`
   are not (already gitignored via `infra/**/*.tfstate` etc.).
2. **plan** — walk the ~10-resource plan together before applying so the
   user (new to Terraform) sees the mapping from `.tf` files to real AWS
   resources.
3. **apply** — expect a 10-20 min wait on CloudFront deployment. Nothing
   else in the plan should be slow.
4. **verify** — run the curl + browser checks from
   `infra/phase0/README.md`:
   - `curl -I https://<domain>` → `200`
   - `curl -I http://<domain>` → `301` to https
   - `curl -I https://www.<domain>` → `200`
   - `curl -I https://<domain>/nonexistent` → `200` (custom error → maintenance page)
   - `curl -sI https://<bucket>.s3.amazonaws.com/index.html` → `403`
   - Browser: legible on mobile.
5. **teardown drill** — Session 1 committed to verifying `terraform destroy`
   is clean before we accumulate more infra. Sequence:
   - `terraform destroy` — expect the CloudFront disable→delete step to
     dominate the runtime (15-30 min).
   - Confirm zero residue in the account (S3 bucket gone, distribution
     gone, Route 53 records gone).
   - `terraform apply` again — leave the maintenance page live.

---

## Decisions locked this session

| Area | Decision |
|---|---|
| `plan -out=tfplan` + `apply "tfplan"` workflow | Adopted as the standard local flow, not plain `terraform apply`. Guarantees the applied plan is exactly the reviewed plan (no drift between plan and apply), and habit-forms the pattern for CI. `tfplan` is a binary blob that can embed sensitive values — gitignored via `infra/**/tfplan` + `infra/**/*.tfplan`, deleted after each apply. |
| `.terraform.lock.hcl` gitignore fix | Removed the line ignoring the lock file. Per HashiCorp guidance the lock file **is** committed — it pins provider binary hashes for reproducible `init` on other machines / CI. Same intent as our strict version pins in `main.tf`, but for the provider bits themselves. |
| Long-blocking commands run by user | Locked in by [[feedback-long-running-commands]]. Terraform `apply` and `destroy` (10-30 min each) are run by the user; Claude runs quick commands only (init, plan, show, verification curls). |

---

## Progress

- ✅ Session log created.
- ✅ `.gitignore` updates: added `infra/**/tfplan` + `infra/**/*.tfplan`; removed the erroneous ignore of `infra/**/.terraform.lock.hcl`.
- ✅ `README.md` updated to use `plan -out=tfplan` → `apply "tfplan"` → `rm tfplan` in both the "First apply" and "Updating the maintenance HTML" sections; explained *why*; corrected resource count from ~10 to 11.
- ✅ `terraform init` — provider 6.54.0 installed, `.terraform.lock.hcl` written.
- ✅ `terraform plan -out=tfplan` walkthrough — 11 to add, 0 change, 0 destroy. Table of resources reviewed with user.
- ✅ `terraform apply "tfplan"` — user ran; distribution reached `Deployed`.
- ✅ Maintenance HTML edit → re-plan (1 change: `aws_s3_object.maintenance_index`) → apply → `aws cloudfront create-invalidation --paths '/index.html' '/'`. Confirmed the update-loop works end to end.
- ✅ Verification block (curl) — 5/5 pass:

  | Check | Result | Meaning |
  |---|---|---|
  | `curl -sI https://<apex>` | `200` | Distribution serving the page over HTTPS |
  | `curl -sI http://<apex>` | `301` | HTTP correctly redirects to HTTPS at the edge |
  | `curl -sI https://www.<apex>` | `200` | www alias works |
  | `curl -sI https://<apex>/nonexistent-path` | `200` | Custom 403/404 → `/index.html` behavior works — every path shows the maintenance page |
  | `curl -sI https://<bucket>.s3.amazonaws.com/index.html` | `403` | Bucket is genuinely private; only CloudFront can read via OAC |

  Response headers on the apex confirm the request path: `via: ... (CloudFront)`, `server: AmazonS3` (upstream), `content-type: text/html; charset=utf-8`.

- ⬜ Verification: browser check at mobile viewport (~375px) on apex + www.
- ✅ Teardown drill — `terraform destroy` removed everything cleanly, user
  confirmed zero AWS residue, `terraform apply "tfplan"` re-created the
  module and the site is back live. Discipline check passed on the first
  attempt.

## Files created / modified this session

- `.claude/sessions/2026-07-15-session-03-phase0-apply.md` — this file
- `.gitignore` — added `infra/**/tfplan` + `infra/**/*.tfplan`; removed the erroneous ignore of `infra/**/.terraform.lock.hcl`
- `infra/phase0/README.md` — swapped `plan`+`apply` for the `plan -out=tfplan` → `apply "tfplan"` → `rm tfplan` workflow in both "First apply" and "Updating the maintenance HTML" sections, with explanation of *why*; corrected resource count
- `infra/phase0/.terraform.lock.hcl` — created by `terraform init` (now trackable after the gitignore fix)
- `infra/phase0/maintenance/index.html` — user edit iterated on during the session (content tweak)

Committed by the user. Per working contract, user runs `git add` / `git commit` themselves.

## Open questions / follow-ups

_(populated as they come up)_
