# CLAUDE.md — aws-wedding-website working contract

This file loads into every Claude Code session on this repo. It captures the rules and workflow conventions that govern how Claude assists on this project.

## Working contract

### Git operations — user-only
Claude **never** runs git write operations on this repo. All `git add`, `git commit`, `git push`, `git tag`, branch deletion, force-push, rebase, reset --hard, revert, or any other operation that mutates local git state or the remote is performed by the user. Read-only inspection (`git status`, `git log`, `git diff`, `git show`, `git remote -v`) is fine.

Claude may propose a commit message or describe what would be staged, but must not execute the commands.

The user stages and commits frequently throughout the session, so an end-of-session `git status` printout is redundant — do not run one as a wrap-up gesture. Running `git status` mid-session for a specific reason (e.g., confirming an in-flight edit landed) is still fine.

### Terraform commands — user-only
Claude **never** runs any `terraform` subcommand that talks to a provider or writes to state or the working directory: this includes `terraform plan`, `terraform apply`, `terraform destroy`, `terraform init`, `terraform import`, `terraform refresh`, `terraform state *`, `terraform taint`/`untaint`, `terraform workspace *`. The user runs all of these and shares back any output that matters (plan diff, apply summary, errors).

Local read-only inspection of Terraform artifacts is fine — reading `.tf` files, reading `terraform.tfstate` (though prefer `terraform output` output pasted by the user), reading planned artifacts the user has already produced (`tfplan` files), `terraform fmt -check`, `terraform validate` (no network, no state write).

Claude may propose the exact command to run and the flags to use, and may describe expected plan output — but must not execute it.

*Why:* Plans and applies for this project touch live AWS state (CloudFront, RDS, EC2 with EIP, S3 buckets holding real photos). The user owns the shell where those commands run so they can see credentials context, cancel mid-plan if something looks off, and keep a mental model of provider drift. Claude driving `plan` divides that ownership in ways that have caused surprises before.

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

### Never guess AWS resource identifiers

Bucket names, ARNs, instance IDs, security group IDs, distribution IDs, hosted zone IDs, ACM cert ARNs, IAM role names, KMS keys, RDS endpoints, **CloudWatch log group names**, **SSM Parameter Store paths** — anything that names a live AWS resource — are **resolved at use-time, never guessed or recalled from memory**. Two authoritative sources:

- **Terraform outputs**: `terraform -chdir=infra/<module> output -raw <name>`. Grep `infra/**/outputs.tf` for the exact output name if unsure.
- **AWS CLI**: `aws <service> describe-*`/`list-*`/`aws logs describe-log-groups`/`aws ssm describe-parameters` etc. — pick the read call that names the thing you need.

This applies in every code path where the identifier lands in front of the user: session logs, handoff commands, PR descriptions, comments in code, shell one-liners you hand to the user to run. If you cannot resolve the identifier in the current environment (no AWS creds, no TF state, sandbox), write a placeholder that makes the resolution step explicit — e.g., `s3://$(terraform -chdir=infra/phase3 output -raw media_bucket_name)/...` — rather than a plausible-looking string. Plausible-looking strings that turn out to be wrong waste the user's time debugging a "why does this AWS command 404" issue that should never have existed.

*Why:* Session 17 hit this twice in one evening — first a guessed media-bucket name (real name is TF-templated `${project_tag}-media-${account_id}` → `wedding-site-media-<account_id>`; user hit `NoSuchBucket`), then a guessed log group name (`/wedding/django` vs real `/wedding-site/django`; diagnostic tail returned `ResourceNotFoundException` and the on-box sync silently continued OOMing the box). Both cost real minutes to diagnose.

### SSM `send-command` payloads — always JSON via jq, never shorthand with escapes

When constructing `aws ssm send-command --parameters` for anything that contains nested quotes (e.g. `sudo -u ec2-user bash -c "..."`), **build the payload as real JSON with jq**:

```
BOX_CMD="sudo -u ec2-user bash -c '…'"
PARAMS=$(jq -n --arg cmd "$BOX_CMD" '{commands: [$cmd]}')
aws ssm send-command --parameters "$PARAMS" …
```

Never use the CLI's `--parameters "commands=[\"...\"]"` shorthand for anything non-trivial. The shorthand parser silently strips embedded quoting on nested `bash -c "..."`, and the on-box command runs with truncated arguments. Symptom: SSM reports `Failed` with stderr like `aws: [ERROR]: the following arguments are required: paths` — because the arguments literally vanished at parse time. This is the same pattern `.github/workflows/deploy.yml` uses; match it.

*Why:* Session 17 lost ~15 min chasing "no output" on a Failed SSM invocation before realizing the shorthand had eaten the `bash -c` inner args.

## Critical rules (from handoff)
- Never use root AWS credentials — IAM admin user only
- Never commit `.env`, `terraform.tfvars`, `*.tfstate`, or any secret-bearing file
- Never hardcode AWS access keys — EC2 uses an instance role, CI uses OIDC
- IAM policies are least-privilege — no `*` on actions or resources
- All CloudWatch log groups need `retention_in_days` set
- Do not enable GuardDuty, Inspector, Security Hub, or Macie — free trials auto-bill on expiry
