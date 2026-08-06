# Session 15 — Ops observability + deploy automation + HSTS

**Date:** 2026-08-05
**Mode:** Execution — CI/CD + logging + hardening
**Model:** Opus 4.7

---

## Context

Session 14 (`2026-08-05-session-14-phase3-cloudfront-and-dns-cutover.md`)
completed the public HTTPS cutover — the site is live at
`https://kaitlynandsteventietheknot.com`, phase 0 is fully destroyed,
phase 3 Terraform state is at 55 resources. Deploy is still manual
(SSH via SSM Session Manager, `git pull`, `pnpm build`,
`collectstatic`, `systemctl restart gunicorn`), there's no branch
protection, and no CloudWatch Agent yet — logs live only on the
instance's journald.

Session 15 closes those gaps and lands the last of the phase 3
handoff items: branch protection, log aggregation with an alarm,
automated deploys via GitHub Actions → SSM, an HSTS soak, and a
one-shot cleanup of the stale static bucket root objects.

Also carrying over a **CI regression** discovered mid-session: the
`frontend` job in `ci.yml` pins `node-version: '20'`, but the repo's
`frontend/package.json` sets `packageManager: pnpm@11.17.0`, and pnpm
11 requires Node ≥ 22.13. Every CI run since Session 14's merge has
failed at `pnpm install --frozen-lockfile`. This is trivially the
first thing to fix.

**Renumber note.** No renumbering needed. Session 16 becomes the
follow-up hardening pass (HSTS ramp to a year + INCLUDE_SUBDOMAINS +
optional preload, deletion protection on RDS, any launch-checklist
prep for the real wedding date).

## Session plan

1. Create this session log (in progress).
2. **CI fix** — bump `.github/workflows/ci.yml` frontend job to
   `node-version: '22'`. Add `node-version-file` if we grow a
   `.node-version` file later; for now the inline pin is fine and
   mirrors what `user_data.sh.tftpl` installs on the EC2 side.
3. **Branch protection** — draft the ruleset spec for the user to
   click through in GitHub Settings. Same shape as S14's handoff but
   with `python` + `frontend` as the required checks (deploy job
   isn't required because it only runs on push-to-main, not on PRs).
4. **CloudWatch Agent + log groups + retention + alarm.**
   - `infra/phase3/cloudwatch.tf`: 3 `aws_cloudwatch_log_group`
     resources (`/wedding-site/django`, `/wedding-site/nginx-access`,
     `/wedding-site/nginx-error`), each with
     `retention_in_days = 30`.
   - `infra/phase3/ssm.tf`: `aws_ssm_parameter` holding the
     CloudWatch Agent config JSON. Agent fetches it via
     `amazon-cloudwatch-agent-ctl -a fetch-config -s -c
     ssm:<param-name>`.
   - `infra/phase3/ec2_iam.tf`: attach AWS-managed
     `CloudWatchAgentServerPolicy` to the EC2 instance role.
   - `infra/phase3/templates/user_data.sh.tftpl`: `dnf install
     amazon-cloudwatch-agent` + start the agent with the SSM-hosted
     config.
   - `infra/phase3/cloudwatch.tf`: metric filter on
     `{ $.level = "ERROR" || $.level = "CRITICAL" }` (matches
     `config.log_formatters.JsonFormatter`'s output shape) →
     `aws_cloudwatch_metric_alarm` → SNS topic → email subscription
     (user's address from CLAUDE.md memory context).
5. **GitHub OIDC provider + deploy role.**
   - `infra/phase3/oidc.tf`: `aws_iam_openid_connect_provider` for
     `token.actions.githubusercontent.com` (thumbprint pinned per
     GitHub's published values).
   - `aws_iam_role` "github-deploy" with trust policy scoped to
     `repo:stnielse/aws-wedding-website:ref:refs/heads/main` — no
     forks, no other branches, no tags.
   - Inline policy:
     - `s3:PutObject` + `s3:PutObjectAcl` on
       `<static-bucket>/deploy/frontend-*.tar.gz` only.
     - `ssm:SendCommand` scoped to the specific EC2 instance ARN +
       the `AWS-RunShellScript` document ARN.
     - `ssm:GetCommandInvocation` + `ssm:ListCommandInvocations` on
       `*` (needed to poll for command completion — no way to scope
       by command ID because you don't have it until after Send).
6. **Deploy workflow** — `.github/workflows/deploy.yml`.
   - `on: push: branches: [main]`, plus
     `workflow_dispatch:` so we can trigger a redeploy manually.
   - `ci` job: `uses: ./.github/workflows/ci.yml` — reruns lint +
     tests through the reusable workflow so we never deploy a broken
     tree.
   - `frontend` job: Node 22 build →
     `tar czf dist.tar.gz -C frontend/dist .` → S3 put via OIDC.
   - `deploy` job: `needs: [ci, frontend]`, SSM SendCommand → poll
     for completion, fail on non-zero.
7. **EC2 deploy script (deploy-only).**
   `scripts/deploy.sh` (repo-tracked, runs as `ec2-user` via SSM):
   args `<git_sha> <artifact_s3_url>`, does `git fetch origin && git
   checkout <sha>`, pip install (in case requirements changed),
   downloads + extracts the frontend tarball to
   `backend/static/frontend/`, runs `migrate` + `collectstatic`,
   `sudo systemctl restart gunicorn`. **Does not** duplicate the
   first-boot flow — user_data still owns fresh-instance bring-up.
8. **HSTS ramp — short soak.** Add
   `SECURE_HSTS_SECONDS = 60` to `backend/config/settings/
   production.py`. Sixty seconds is short enough that a botched
   HTTPS deploy is recoverable inside a minute, long enough that
   we're actually exercising the header path. Add a matching test.
   Full ramp to `31536000` + INCLUDE_SUBDOMAINS is Session 16.
9. **Static bucket root cleanup.**
   `scripts/cleanup_static_bucket_root.py` — dry-run by default,
   lists every object at the root of the static bucket
   (`prefix=""`, excludes anything under `static/`), prints counts,
   confirms, then deletes. User runs it once and we delete the
   script (or keep it for future reference; TBD).
10. `terraform -chdir=infra/phase3 fmt -diff` + non-ASCII grep on
    the new files (per [[feedback-aws-ascii-only-descriptions]]).
11. Django test suite green (should be 56 tests: 55 baseline + 1
    HSTS test).
12. Hand user (a) `terraform plan` + `apply` in phase 3, (b)
    branch protection UI steps, (c) static bucket cleanup script,
    (d) commit + push to trigger first automated deploy — plus
    verify SNS subscription confirmation email.
13. Finalize this log.

---

## Decisions locked this session

### Frontend build ships via S3 tarball, not built on the box

| Area | Decision |
|---|---|
| Choice | CI builds `frontend/dist/`, tars it as `frontend-<sha>.tar.gz`, uploads to `s3://<static-bucket>/deploy/`. The EC2 deploy script downloads + extracts to `backend/static/frontend/`, then `collectstatic` moves the hashed assets into the static bucket under `static/`. |
| Why | Two wins. (1) Speed — Vite build on t3.micro was measured at ~40s in Session 13; CI does it in ~10s and the deploy step just untars, which is single-digit seconds. (2) RAM headroom — `pnpm build` was the peak RAM consumer on the t3.micro (1 GiB total), occasionally OOM-nudged by gunicorn workers still serving traffic during deploys. Reusing the static bucket for artifacts means no new bucket, no new IAM surface — the EC2 role already reads it. |

### GitHub OIDC federation, no long-lived AWS keys in the repo

| Area | Decision |
|---|---|
| Choice | Provision an `aws_iam_openid_connect_provider` and a role assumable **only** by `repo:stnielse/aws-wedding-website:ref:refs/heads/main`. The deploy workflow uses `aws-actions/configure-aws-credentials` with `role-to-assume` — no secrets in `.github/workflows/*.yml`, no long-lived access keys. |
| Why | Per project critical rules (see CLAUDE.md): "EC2 uses an instance role, CI uses OIDC" — this is that. Locking the `sub` claim to `ref:refs/heads/main` means a compromised PR from a fork can't assume the role. |

### SSM SendCommand as the deploy trigger (not SSH)

| Area | Decision |
|---|---|
| Choice | Deploy job invokes SSM `AWS-RunShellScript` document targeting the EC2 instance by ID. Command body: `sudo -u ec2-user /home/ec2-user/aws-wedding-website/scripts/deploy.sh <sha> <artifact_url>`. Wait for `GetCommandInvocation` to return `Success`; fail the workflow otherwise. |
| Why | Port 22 stays closed (already the case — SG has no 22 ingress). No SSH key management, no bastion. The EC2 role already has SSM Session Manager, and adding SendCommand permission to the *GitHub* role means the audit trail lives in CloudTrail with a distinct principal (`arn:...:role/github-deploy` vs. anyone who runs `aws ssm start-session` interactively). |

### CloudWatch Agent config lives in SSM Parameter Store, not baked into user_data

| Area | Decision |
|---|---|
| Choice | Store the agent config JSON as an `aws_ssm_parameter` (String, tier Standard). user_data runs `amazon-cloudwatch-agent-ctl -a fetch-config -s -c ssm:/wedding-site/prod/CLOUDWATCH_AGENT_CONFIG`. |
| Why | Editing what the agent tails becomes a Terraform apply that updates one param + a single SSM RunCommand to `amazon-cloudwatch-agent-ctl -a fetch-config` on the instance — no user_data rerun, no instance replace. Baking into user_data would require an instance replace for every log-shape tweak. |

### Log group naming: `/wedding-site/<component>`, not Django-idiomatic paths

| Area | Decision |
|---|---|
| Choice | Three log groups: `/wedding-site/django`, `/wedding-site/nginx-access`, `/wedding-site/nginx-error`. All under one `/wedding-site/` prefix, easily filterable in the console. Retention 30 days. |
| Why | Consistency with `local.ssm_prefix = "/wedding-site/prod"`. Retention 30 days balances "long enough to debug last-week issues" against "log costs match traffic" — at anticipated request volume (a few hundred hits/day peak, ~50 guests) this is pennies. |

### Alarm on ERROR/CRITICAL JSON records, single SNS email subscription

| Area | Decision |
|---|---|
| Choice | Metric filter pattern `{ ($.level = "ERROR") || ($.level = "CRITICAL") }` on `/wedding-site/django`. Alarm: `Sum` over 5 min, threshold ≥ 1, evaluation periods = 1. SNS topic → email subscription to `s.conwaynielsen@gmail.com`. |
| Why | The `JsonFormatter` emits `level` as a top-level key, so the metric filter matches Django's WARNING/ERROR/CRITICAL levels natively. Sensitivity is intentionally tight — this is a wedding site, ERROR-rate should be zero at steady state. False positives are cheap; missed real errors are what we're avoiding. |

### HSTS: 60 seconds this session, not 31536000

| Area | Decision |
|---|---|
| Choice | `SECURE_HSTS_SECONDS = 60`. No INCLUDE_SUBDOMAINS, no PRELOAD. |
| Why | HSTS is one-way: browsers pin the header for `max_age`. Sixty seconds means any HTTPS breakage recovers in a minute, but we're exercising the actual code path. Session 16 ramps to a year once we've soaked without incident. |

### `ci.yml` becomes reusable; `deploy.yml` calls it via `workflow_call`

| Area | Decision |
|---|---|
| Choice | Refactor `.github/workflows/ci.yml` to expose its `python` + `frontend` jobs via `on: workflow_call:`. `deploy.yml` declares `jobs.ci: uses: ./.github/workflows/ci.yml`, then `jobs.deploy: needs: [ci]` proceeds only when both pass. |
| Why | One test/lint definition, one source of truth. Alternatives were: (a) copy-paste — drift risk; (b) trust that branch protection already ran ci — skips revalidation on `workflow_dispatch` and doesn't cover a direct-to-main push if bypass ever fires. Reusable workflows are a first-class GitHub Actions feature; the refactor is a two-line addition. |

### Frontend build runs exactly once per deploy; artifact flows via GHA upload/download

| Area | Decision |
|---|---|
| Choice | `ci.yml` frontend job takes a `workflow_call` boolean input `upload_artifact` (default false). When true, the job uploads `backend/static/frontend/` as a GHA artifact named `frontend-dist` (retention 7d). `deploy.yml` calls ci.yml with `upload_artifact: true`, then a single `deploy` job downloads the artifact, tars it, ships to S3, and fires SSM SendCommand. |
| Why | Naive approach was to have deploy.yml re-run `pnpm build` after `ci` reported green — that pays for the build twice per deploy (~10s each). Alternatives considered: (a) drop `pnpm build` from ci.yml entirely — loses PR-time regression detection; (b) fold the S3 upload into ci.yml — mixes CI verification concerns with deploy-specific AWS knowledge (S3 bucket, OIDC role). The GHA-artifact hand-off keeps ci.yml purely about verification (with an optional side effect gated by the caller) and keeps AWS specifics in deploy.yml. PR-triggered CI runs still don't upload anything — the `if: ${{ inputs.upload_artifact }}` guard means the extra step only fires when deploy calls it. |

### First-boot and deploy stay on separate code paths

| Area | Decision |
|---|---|
| Choice | `scripts/deploy.sh` is deploy-only — assumes venv + git clone already exist, downloads the frontend tarball, runs migrate + collectstatic + restart. `user_data.sh.tftpl` keeps its inline first-boot app-tier flow (clone, pip install, local `pnpm build`, migrate, collectstatic, start systemd units) unchanged in shape — only the CloudWatch Agent install gets added. |
| Why | First boot happens ~2× in the site's whole life; deploys happen ~50–100×. Optimizing the frequent path to be simple and standalone (no "no artifact URL → build locally" branch, no dual invocation context) matters more than deduplicating three lines of migrate/collectstatic/restart. Shared-script complexity pays off in high-churn systems with many environments — not here. |

### Static bucket cleanup is user-run, not CI-run

| Area | Decision |
|---|---|
| Choice | `scripts/cleanup_static_bucket_root.py` runs locally against the user's SSO creds. Not wired into the deploy workflow. |
| Why | One-shot cleanup of pre-Session-14 artifacts; putting it in CI creates a footgun (future misconfig deletes real assets). Also matches [[feedback-long-running-commands]] — the user should have eyes on any shared-state mutation. |

---

## Progress

- [ ] Session log created (this file).
- [ ] `.github/workflows/ci.yml` — Node bump 20 → 22.
- [ ] Branch protection instructions drafted for user.
- [ ] `infra/phase3/cloudwatch.tf` — log groups + metric filter + alarm + SNS topic.
- [ ] `infra/phase3/ssm.tf` — CLOUDWATCH_AGENT_CONFIG param.
- [ ] `infra/phase3/ec2_iam.tf` — CloudWatchAgentServerPolicy attached.
- [ ] `infra/phase3/templates/user_data.sh.tftpl` — agent install + fetch-config.
- [ ] `infra/phase3/oidc.tf` — OIDC provider + github-deploy role.
- [ ] `.github/workflows/ci.yml` — add `workflow_call:` trigger so deploy can reuse.
- [ ] `.github/workflows/deploy.yml` — full three-job workflow (ci → frontend → deploy).
- [ ] `scripts/deploy.sh` — EC2 deploy script (deploy-only, no first-boot overlap).
- [ ] `backend/config/settings/production.py` — HSTS 60s.
- [ ] `backend/config/tests.py` — HSTS test.
- [ ] `scripts/cleanup_static_bucket_root.py` — dry-run + confirm + delete.
- [ ] `terraform validate` + `fmt -diff` + non-ASCII grep clean.
- [ ] Django test suite green.
- [ ] User: `terraform plan` + `apply` in phase 3.
- [ ] User: branch protection UI steps.
- [ ] User: SNS subscription confirmation.
- [ ] User: static bucket cleanup script run.
- [ ] User: commit + push to trigger first automated deploy — verify.
- [ ] Session log finalized.

## Digressions worth remembering

*(Filled in during execution.)*

---

## User execution checklist

Steps the user runs at the end of the session (Claude does not run
git write ops per [[feedback-git-operations]], nor long-running
`terraform apply` per [[feedback-long-running-commands]]).

### 1 — Branch protection on `main` (GitHub UI)

**Settings → Rules → Rulesets → New branch ruleset:**

- **Ruleset name:** `main-protected`
- **Enforcement status:** Active
- **Target branches:** Include default branch (`main` only)
- **Rules to enable:**
  - Restrict deletions
  - Block force pushes
  - Require a pull request before merging
    - Required approvals: `0` (solo project, keeps the PR workflow)
    - Require conversation resolution before merging
  - Require status checks to pass
    - Select the two CI job names once they've reported at least once
      on a PR: **`ci / python`** and **`ci / frontend`** (the `ci /`
      prefix comes from `deploy.yml` calling `ci.yml` via
      `workflow_call`; check names show up in the picker as
      `<caller-job-id> / <called-job-name>`).
    - Require branches to be up to date before merging
- **Bypass list:** add `stnielse` as Role: Repository admin, Mode:
  Always. Emergency direct-push valve; every other push goes through
  PR + CI.

**Verify:** open a throwaway branch, push a whitespace-only commit
to `main` directly → should be rejected. Open a real PR against
`main`, confirm the two `ci / *` checks appear as "Required."

### 2 — SSO login + `terraform apply` (phase 3)

```
aws sso login
cd infra/phase3
terraform plan -out=tfplan
# review: expect ~10 new resources (log groups, SNS topic +
# subscription, metric filter, alarm, OIDC provider, deploy role +
# policy, ssm param for cw agent config), plus updates to
# ec2_iam.tf (attach CloudWatchAgentServerPolicy) and user_data.
terraform apply tfplan
```

The user_data changes trigger nothing on the running instance
(`user_data_replace_on_change = false`). To install the CloudWatch
Agent on the *existing* instance without waiting for the next
replace, SSM Session Manager into the box and run:

```
sudo dnf -y install amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -s -m ec2 \
  -c ssm:/wedding-site/prod/CLOUDWATCH_AGENT_CONFIG
```

### 3 — SNS subscription confirmation

Check `s.conwaynielsen@gmail.com` inbox for an "AWS Notification —
Subscription Confirmation" email from `no-reply@sns.amazonaws.com`.
Click the confirm link.

### 4 — Static bucket root cleanup

```
cd /Users/stevennielsen/aws-wedding-website
.venv/bin/python scripts/cleanup_static_bucket_root.py --dry-run
# review the count (should list ~343 objects), then:
.venv/bin/python scripts/cleanup_static_bucket_root.py --yes
```

### 5 — Commit + push to trigger first automated deploy

Stage everything from this session, commit, push to `main`.
Watch the Actions tab: `deploy` workflow should trigger, `ci` jobs
pass, `frontend` uploads the tarball, `deploy` fires SSM SendCommand,
waits for `Success`. Verify by hitting
`https://kaitlynandsteventietheknot.com` — the new git SHA should
show up in whatever page has a git-sha footer (or via SSM
`aws ssm start-session ...` then `cd /home/ec2-user/aws-wedding-website
&& git rev-parse HEAD`).

---

## Files created / modified this session

*(Filled in during execution.)*

**Created:**
- `.claude/sessions/2026-08-05-session-15-ops-and-deploy.md` — this log

## Session 16 handoff

*(Filled in during execution.)*

## Open questions / follow-ups

*(Carried from Session 14 unless noted.)*

- Q1 dietary + Q6 schedule — still open from Session 7.
- Photo alt-text values — final copy still pending.
- Deletion protection on RDS — flip closer to the wedding.
- `<picture>` mobile crop for hero — Session 16+.
- `django-vite` — still deferred.
- Real gallery page — Session 16+.
- HSTS full ramp (60 → 31536000, INCLUDE_SUBDOMAINS, PRELOAD, submit to hstspreload.org) — Session 16 after soak.
