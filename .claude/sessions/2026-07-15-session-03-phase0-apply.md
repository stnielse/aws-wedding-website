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

_(populated as they come up)_

---

## Progress

- ✅ Session log created.
- ⬜ `terraform init`
- ⬜ `terraform plan` walkthrough
- ⬜ `terraform apply`
- ⬜ Verification block (curl + browser)
- ⬜ Teardown drill (destroy → verify clean → re-apply)

## Files created / modified this session

- `.claude/sessions/2026-07-15-session-03-phase0-apply.md` — this file

_(Terraform will create `.terraform.lock.hcl` on init — that file is
committed. `terraform.tfvars` and state files remain gitignored.)_

## Open questions / follow-ups

_(populated as they come up)_
