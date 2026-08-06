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

- [x] Session log created (this file).
- [x] `.github/workflows/ci.yml` — Node bump 20 → 22, `workflow_call:` trigger, `upload_artifact` input + optional artifact upload.
- [x] Branch protection instructions drafted (see User execution checklist below).
- [x] `infra/phase3/cloudwatch.tf` — 3 log groups + metric filter + alarm + SNS topic + email subscription.
- [x] `infra/phase3/ssm.tf` — CLOUDWATCH_AGENT_CONFIG param (files: nginx access/error + journald: gunicorn.service).
- [x] `infra/phase3/ec2_iam.tf` — CloudWatchAgentServerPolicy attached to EC2 role.
- [x] `infra/phase3/templates/user_data.sh.tftpl` — agent install + fetch-config + passwordless sudo for `systemctl restart gunicorn`.
- [x] `infra/phase3/oidc.tf` — OIDC provider + github-deploy role scoped to `refs/heads/main`.
- [x] `infra/phase3/variables.tf` + `terraform.tfvars.example` — new `alert_email` and `github_repository` variables.
- [x] `infra/phase3/outputs.tf` — CloudWatch + SNS + github-deploy role outputs.
- [x] `.github/workflows/deploy.yml` — two-job workflow (ci via workflow_call → deploy: download artifact → tar → S3 → SSM SendCommand → poll → surface output).
- [x] `scripts/deploy.sh` — EC2 deploy script (deploy-only, no first-boot overlap).
- [x] `backend/config/settings/production.py` — `SECURE_HSTS_SECONDS = 60`.
- [x] `backend/config/tests.py` — HSTS test.
- [x] `scripts/cleanup_static_bucket_root.py` — dry-run default + `--yes` confirm + batched delete.
- [x] `terraform validate` clean; `fmt` applied; non-ASCII grep only hits pre-existing em-dash in a Terraform *output* description (not an AWS resource description — same tolerance as Session 14).
- [x] Django test suite green — 56 tests, ok (55 baseline + 1 new HSTS test).
- [ ] User: `terraform plan` + `apply` in phase 3.
- [ ] User: set the 3 GitHub Actions repo variables (`AWS_DEPLOY_ROLE_ARN`, `STATIC_BUCKET_NAME`, `EC2_INSTANCE_ID`) from the terraform outputs.
- [ ] User: install `amazon-cloudwatch-agent` on the existing instance via SSM Session Manager (see checklist).
- [ ] User: branch protection UI steps.
- [ ] User: SNS subscription confirmation.
- [ ] User: static bucket cleanup script run.
- [ ] User: commit + push to trigger first automated deploy — verify.
- [x] Session log finalized.

## Digressions worth remembering

**1. CI was broken since Session 14 merge (Node 20 vs. pnpm 11 mismatch).**
User surfaced this at session start: `frontend` job in `ci.yml`
pinned `node-version: '20'`, but `frontend/package.json` sets
`packageManager: pnpm@11.17.0`, and pnpm 11 requires Node ≥ 22.13
— so `pnpm install --frozen-lockfile` failed on every CI run. Fix
was a one-line bump to `'22'`. **Lesson:** when a project pins
`packageManager` in `package.json`, the CI Node version pin has to
be compatible or install will fail cryptically. Worth grepping
`packageManager` in `package.json` before pinning Node in any new
workflow, and worth revisiting whenever the pnpm major bumps.

**2. Deploy workflow's frontend duplication → single-build refactor mid-write.**
First draft of `deploy.yml` had its own frontend build job — CI
would build (for verification), then deploy would build again (for
the artifact). User caught the asymmetry and asked why. Turned out
Options B (upload-artifact from ci.yml → download-artifact in
deploy.yml) was cleanly reachable: `ci.yml` grew a `workflow_call`
input `upload_artifact` (default false), guarded the upload step
behind it, and `deploy.yml` collapsed to a single `deploy` job.
**Lesson:** when a "reusable workflow" plus a "deploy workflow"
both need the same build output, the artifact-flow question deserves
explicit design — don't just duplicate the build. Also: PR-triggered
runs of ci.yml still don't upload anything (the input defaults to
false), so PRs stay fast.

**3. CloudWatch Agent doesn't accept `journald` under `logs.logs_collected`.**
First draft of `ssm.tf`'s agent config had a `journald` block
pointing at the `gunicorn.service` unit. Install succeeded on the
running instance, but `amazon-cloudwatch-agent-ctl -a fetch-config`
returned `Under path : /logs/logs_collected | Error : Additional
property journald is not allowed` and the agent never started.
amazon-cloudwatch-agent 1.300.x only supports `files`,
`windows_events`, and `emf` under `logs_collected` — the "collect
from systemd journal" feature I remembered doesn't actually exist
in this codebase. Fix: switched `gunicorn.service.tftpl` from
`StandardOutput=journal` to `StandardOutput=append:/var/log/
gunicorn/gunicorn.log`, added a matching `files` entry to the
agent config, and added a `/etc/logrotate.d/gunicorn` drop-in
(`copytruncate`, daily, keep 14) so the file doesn't grow
unbounded. **Lesson:** don't assume agent feature availability
from memory — the schema is narrow, and the file-based path is
the actually-supported one.

**3b. `LogsDirectory=` doesn't race-safe-create the directory before `append:` opens the file.**
First recovery attempt trusted systemd's `LogsDirectory=gunicorn`
to create `/var/log/gunicorn/` at service start. It did not —
gunicorn failed 30+ restart attempts with `Failed at step STDOUT
spawning ...: No such file or directory` (exit 209/STDOUT).
`StandardOutput=append:PATH` opens the file during pre-exec setup,
apparently before `LogsDirectory=` materializes the directory (or
systemd's LogsDirectory only creates when User= is a dynamic user,
not our real ec2-user — the exact ordering is undocumented enough
that I stopped chasing it). Fix: pre-create the directory
explicitly in both `user_data.sh.tftpl` (already done via
`LogsDirectory=` for fresh boots, plus the same directory is
recreated by the fix script on existing boxes) and in the recovery
script (`install -d -o ec2-user -g ec2-user -m 0755
/var/log/gunicorn`). Kept `LogsDirectory=` in the unit for defense
in depth; the explicit `install -d` is the real guarantee.
**Lesson:** systemd's implicit directory creation directives are
convenient but not reliable enough to build a service open on.
When `StandardOutput=append:` (or any file-open pre-exec directive)
depends on a directory, make sure the directory exists via a real,
explicit `install -d` or `mkdir -p` before the first restart.

**3c. SSM SendCommand with a multi-line script blob triggered "cannot execute: required file not found."**
Recovery attempt via `send-command --parameters commands=[<big_
multiline_script>]` failed with exit 127 at the shebang. The
script file the SSM agent wrote to disk had a valid shebang and
LF endings, but AWS's wrapper apparently exec'd the file directly
via a path where the shebang interpreter lookup failed (root
cause not diagnosed). Working fix: base64-encode the script on the
Mac, send a single-line command `echo <b64> | base64 -d | bash`.
No file on disk, no shebang, no exec dance. **Lesson:** for any
non-trivial SSM SendCommand payload, prefer base64+pipe over
multi-line `commands` arrays — it's paste-safe, shebang-free, and
avoids AWS's wrapper quirks entirely.

**3d. Branch protection required checks never satisfied due to trigger-suffix collision.**
Initial `ci.yml` had `on: [push, pull_request, workflow_call]`.
On every push to a PR branch, GitHub fired ci twice (once per
event) and disambiguated the check names by appending
`(push)` / `(pull_request)` — so the actual check runs were named
`ci / python (push)` and `ci / python (pull_request)`. Branch
protection required `ci / python` (no suffix), which never
appeared, so PRs stayed pending "Expected — Waiting for status to
be reported" indefinitely. Fix: drop `on: push` from ci.yml so
only one event ever triggers per PR, which removes the suffix and
makes the check names match branch protection's expectation.
`workflow_call` stayed (deploy.yml still reuses ci.yml on push to
main). **Lesson:** when the same workflow can be triggered by
multiple events on the same ref, GitHub disambiguates check names
by tacking the event on — and branch protection's required-check
selector matches the exact name, suffix included. Pick one PR-time
trigger and stick with it.

**4. `ssm:GetCommandInvocation` can't be resource-tag-scoped.**
Wanted to scope the deploy role's `GetCommandInvocation` to only
the wedding-site instance via a `ssm:resourceTag/Name` condition.
Doesn't work — command-invocation resources aren't tagged the way
EC2 instances are, so the condition wouldn't match and every call
would fail. Ended up with `Resource: *` and a comment noting the
role's trust policy (main-branch-of-this-repo only) is the actual
scoping mechanism.

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

### 5 — Set GitHub Actions repo variables

Populate from `terraform -chdir=infra/phase3 output`:

- `AWS_DEPLOY_ROLE_ARN` ← `github_deploy_role_arn`
- `STATIC_BUCKET_NAME`  ← `static_bucket_name`
- `EC2_INSTANCE_ID`     ← `ec2_instance_id`

Settings → Secrets and variables → Actions → Variables → New
repository variable. All three are **plaintext variables** (not
secrets). The deploy workflow reads them via `${{ vars.NAME }}`.

### 6 — Commit + push to trigger first automated deploy

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

**Created:**
- `.claude/sessions/2026-08-05-session-15-ops-and-deploy.md` — this log
- `.github/workflows/deploy.yml`
- `infra/phase3/cloudwatch.tf`
- `infra/phase3/oidc.tf`
- `scripts/deploy.sh`
- `scripts/cleanup_static_bucket_root.py`

**Modified:**
- `.github/workflows/ci.yml` (Node 22, workflow_call trigger, optional artifact upload)
- `infra/phase3/variables.tf` (added `alert_email`, `github_repository`)
- `infra/phase3/terraform.tfvars.example` (documented the two new vars)
- `infra/phase3/outputs.tf` (CloudWatch, SNS, github-deploy role outputs)
- `infra/phase3/ssm.tf` (CLOUDWATCH_AGENT_CONFIG param)
- `infra/phase3/ec2_iam.tf` (attach CloudWatchAgentServerPolicy)
- `infra/phase3/templates/user_data.sh.tftpl` (agent install + fetch-config, passwordless sudo drop-in)
- `backend/config/settings/production.py` (SECURE_HSTS_SECONDS = 60)
- `backend/config/tests.py` (HSTS test)

Per working contract, all `git add` / `git commit` is left to the
user.

## Session 16 handoff

Session 16 = **HSTS full ramp + RDS deletion protection + real
gallery page + any launch-checklist prep.** Ordered by risk/urgency:

### Step 1 — HSTS ramp (assuming Session 15's 60s soak is clean)

If two weeks of green deploys + healthy alarm output have gone by
without any HTTPS regression:

1. `SECURE_HSTS_SECONDS = 3600` — one-hour commitment. Push,
   verify browsers pin correctly.
2. `SECURE_HSTS_SECONDS = 604800` — one week.
3. `SECURE_HSTS_SECONDS = 31536000` + `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`.
4. Optionally add `SECURE_HSTS_PRELOAD = True` and submit the
   domain to https://hstspreload.org (irreversible for the
   preload list — only do this once the wedding is over or
   you're 100% committed to HTTPS forever on this domain).

Each step just needs a settings change + push (the deploy workflow
handles the rest). Update `test_hsts_seconds_set_to_soak_value` at
each ramp so the test is a real assertion.

### Step 2 — RDS deletion protection

`aws_db_instance.wedding` has `deletion_protection = false` today
(so tearing down phase 3 in dev is easy). Once we're closer to the
wedding (Session 14+15 handoffs said "flip pre-wedding"), flip to
`true`. A `terraform apply` with only that change is safe and
non-disruptive.

### Step 3 — Real gallery page

Session 9 landed the home-page photo strip. The real gallery view
(Session 8's `Gallery` React island against `/api/photos/`) is
still stubbed. Design + implement.

### Step 4 — Launch checklist

Compile from prior sessions' notes: create a prod Django superuser
via SSM (Session 14 lesson), verify SNS confirmation, verify HSTS,
verify branch protection enforcement, verify deploy workflow end-
to-end from a real push. Draft as `.claude/launch-checklist.md`.

### Step 5 — Post-deploy CloudFront invalidation (optional)

`deploy.sh` doesn't create a CloudFront invalidation today. Since
static assets are hashed by `ManifestS3StaticStorage`, an
invalidation isn't strictly required — new deploys ship new
filenames and the templates reference them. But `/index.html` and
Django-rendered HTML pages *are* dynamic (from the EC2 origin,
`CachingDisabled`), so they're never cached either. The only case
that would benefit from invalidation is if we ever cache the
default behavior, which we don't. Skip unless caching strategy
changes.

## Open questions / follow-ups

*(Carried from Session 14 unless noted.)*

- Q1 dietary + Q6 schedule — still open from Session 7.
- Photo alt-text values — final copy still pending.
- Deletion protection on RDS — flip closer to the wedding.
- `<picture>` mobile crop for hero — Session 16+.
- `django-vite` — still deferred.
- Real gallery page — Session 16+.
- HSTS full ramp (60 → 31536000, INCLUDE_SUBDOMAINS, PRELOAD, submit to hstspreload.org) — Session 16 after soak.
