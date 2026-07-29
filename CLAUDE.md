# CLAUDE.md — aws-wedding-website working contract

This file loads into every Claude Code session on this repo. It captures the rules and workflow conventions that govern how Claude assists on this project.

## Working contract

### Git operations — user-only
Claude **never** runs git write operations on this repo. All `git add`, `git commit`, `git push`, `git tag`, branch deletion, force-push, rebase, reset --hard, revert, or any other operation that mutates local git state or the remote is performed by the user. Read-only inspection (`git status`, `git log`, `git diff`, `git show`, `git remote -v`) is fine.

Claude may propose a commit message or describe what would be staged, but must not execute the commands.

The user stages and commits frequently throughout the session, so an end-of-session `git status` printout is redundant — do not run one as a wrap-up gesture. Running `git status` mid-session for a specific reason (e.g., confirming an in-flight edit landed) is still fine.

### Session logs
Every non-trivial working session begins by creating a session log at `.claude/sessions/YYYY-MM-DD-session-NN-<slug>.md`. The log captures context, decisions locked, issues resolved, open questions, files touched, and a running progress checklist. See `.claude/sessions/2026-07-13-session-01-design.md` for the canonical template.

Trivial one-off fixes (typo, single-file question) do not need a session log. Sessions that make design or scope decisions always do.

### Tests before finalization
Unit tests are the **penultimate step** of every session that ships code — written and passing *before* the session log gets finalized. The order is: implementation → smoke test → tests written and passing → session log finalized. Never finalize the log with tests still in a `[ ]` progress checkbox; a session that couldn't land its tests documents *why* under "Digressions" and leaves the checkbox unchecked so the next session's handoff picks it up.

## Project context

Self-hosted wedding website targeting live-and-stable by end of June 2026. Full scope, architecture, models, and phase plan live in `.claude/wedding-site-handoff.md` — that document is the source of truth for the build.

### Stack summary
- **Backend:** Django (LTS) + templates + HTMX; Django admin for guest management
- **Frontend:** Vite + React islands (`RsvpForm`, `Gallery`) mounted into Django templates
- **Database:** PostgreSQL on RDS (db.t3.micro)
- **Media:** S3 (private) served via CloudFront OAC
- **Compute:** EC2 t3.micro on **Amazon Linux 2023** (dnf, `ec2-user`)
- **CDN/TLS:** CloudFront, ACM cert in us-east-1
- **IaC:** Terraform for every AWS resource; `terraform destroy` must be clean
- **CI/CD:** GitHub Actions → SSM `send-command`, OIDC federation (no long-lived keys)

### Local paths (pinned — do not search for these)
- **Django Python interpreter:** `/Users/stevennielsen/aws-wedding-website/.venv/bin/python`
  - Use this exact path for every `manage.py` / `pip` / `django-admin` invocation. Do not `which python`, `ls .venv`, or otherwise probe for it — it lives at repo root, not under `backend/`.
  - Repo-relative equivalent (from repo root): `.venv/bin/python`
- **Django project root:** `/Users/stevennielsen/aws-wedding-website/backend/` (where `manage.py` lives).
- **Frontend root:** `/Users/stevennielsen/aws-wedding-website/frontend/`. Use `pnpm` via corepack (`packageManager` field in `frontend/package.json` pins the version).
- **Runserver port:** `8765`. **Vite dev server:** `http://localhost:5175/` — NOT `127.0.0.1` (Vite 8 quirk from Session 6).

## Critical rules (from handoff)
- Never use root AWS credentials — IAM admin user only
- Never commit `.env`, `terraform.tfvars`, `*.tfstate`, or any secret-bearing file
- Never hardcode AWS access keys — EC2 uses an instance role, CI uses OIDC
- IAM policies are least-privilege — no `*` on actions or resources
- All CloudWatch log groups need `retention_in_days` set
- Do not enable GuardDuty, Inspector, Security Hub, or Macie — free trials auto-bill on expiry
