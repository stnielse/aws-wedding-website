# CLAUDE.md — aws-wedding-website working contract

This file loads into every Claude Code session on this repo. It captures the rules and workflow conventions that govern how Claude assists on this project.

## Working contract

### Git operations — user-only
Claude **never** runs git write operations on this repo. All `git add`, `git commit`, `git push`, `git tag`, branch deletion, force-push, rebase, reset --hard, revert, or any other operation that mutates local git state or the remote is performed by the user. Read-only inspection (`git status`, `git log`, `git diff`, `git show`, `git remote -v`) is fine.

Claude may propose a commit message or describe what would be staged, but must not execute the commands.

### Session logs
Every non-trivial working session begins by creating a session log at `.claude/sessions/YYYY-MM-DD-session-NN-<slug>.md`. The log captures context, decisions locked, issues resolved, open questions, files touched, and a running progress checklist. See `.claude/sessions/2026-07-13-session-01-design.md` for the canonical template.

Trivial one-off fixes (typo, single-file question) do not need a session log. Sessions that make design or scope decisions always do.

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

## Critical rules (from handoff)
- Never use root AWS credentials — IAM admin user only
- Never commit `.env`, `terraform.tfvars`, `*.tfstate`, or any secret-bearing file
- Never hardcode AWS access keys — EC2 uses an instance role, CI uses OIDC
- IAM policies are least-privilege — no `*` on actions or resources
- All CloudWatch log groups need `retention_in_days` set
- Do not enable GuardDuty, Inspector, Security Hub, or Macie — free trials auto-bill on expiry
