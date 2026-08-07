# Session 16 — Deploy bootstrap fix + self-healing SSM guard

**Date:** 2026-08-06
**Mode:** Execution — CI/CD hardening
**Model:** Opus 4.7

---

## Context

Session 15 (`2026-08-05-session-15-ops-and-deploy.md`) landed the
automated deploy pipeline (OIDC → S3 → SSM SendCommand →
`scripts/deploy.sh`) but the very first automated run on
2026-08-05 failed with:

```
sudo: /home/ec2-user/aws-wedding-website/scripts/deploy.sh: command not found
```

Chicken-and-egg: `scripts/deploy.sh` was created in the same PR
that first triggered `deploy.yml`. The running EC2 instance's git
checkout is from Session 12/13 (pre-`scripts/deploy.sh`), and the
new deploy workflow's SSM SendCommand tried to `sudo -u ec2-user`
a file that didn't yet exist on the box.

S15 handoff documented the fix as S16 Step 0 (urgent). This session
is that fix — a one-time bootstrap on the running instance to
advance its checkout past `fc0498e` ("deploy script"), plus a
prophylactic edit to `deploy.yml`'s SSM command body so that any
future new-file-under-`scripts/` add self-heals rather than failing
the first deploy after the add.

**Repo state check at session start:**
- `git log main` — tip is `37ad71b`; `scripts/deploy.sh` first
  appears in `fc0498e`, well below tip. So main is fine — only the
  running box is behind.
- Current branch `miscellaneous-template-updates` is 5 commits
  ahead of main (kids FAQ, registry copy, date tweaks, teaser-3
  jpg). These are unrelated to the S16 fix; they'll get their own
  PR when the user is ready.

**Renumber note.** No renumbering needed. S16 in the S15 handoff
already covered five items (bootstrap, HSTS ramp, RDS deletion
protection, real gallery, launch checklist); this session takes
the urgent one (bootstrap) and leaves the rest for S17+.

## Session plan

1. Create this session log (in progress).
2. **Draft the one-time SSM bootstrap command** the user runs from
   the Mac to `git pull` the instance to current main HEAD. This
   is the actual unblock — once the box has `scripts/deploy.sh` on
   disk, the existing `deploy.yml` (unmodified) works.
3. **Edit `.github/workflows/deploy.yml`** to prepend a
   `git fetch + git checkout $SHA` step to the SSM RunCommand body.
   Wrapped in `sudo -u ec2-user bash -c '…'` with `set -e` so the
   pre-guard failure fails the whole invocation. This is
   redundant with `scripts/deploy.sh`'s own internal fetch +
   checkout (lines 37–38), but that redundancy is the point — if
   `scripts/deploy.sh` doesn't exist yet at the checkout the box
   is on, we never reach its internal fetch. The pre-guard is
   what materializes the file.
4. `yaml.safe_load` deploy.yml to catch any YAML shape breakage
   from the multi-line jq change; non-ASCII grep on files touched.
5. Django test suite unchanged (this is a workflow YAML change —
   no unit test surface). Note this explicitly under Digressions
   so the CLAUDE.md tests-before-finalization rule stays honest.
6. Hand user: (a) SSM bootstrap command, (b) merge path for the
   deploy.yml edit — probably a small standalone PR ahead of the
   `miscellaneous-template-updates` branch so the fix lands on
   main before the next deploy fires, (c) verify next deploy on
   Actions tab.
7. Finalize this log.

---

## Decisions locked this session

### The pre-guard aligns to `$SHA`, not just `main` HEAD

| Area | Decision |
|---|---|
| Choice | SSM body: `git fetch --prune origin && git checkout --detach $SHA` before invoking `scripts/deploy.sh`. Same shape as what `deploy.sh` does internally at lines 37–38. |
| Why | Aligning the working tree to the exact deploy `$SHA` (rather than to `main` HEAD or `origin/main`) matches what the rest of the deploy flow assumes and avoids any window where the box briefly has a newer main HEAD than the artifact was built from. The redundancy with `deploy.sh`'s internal fetch/checkout is cheap (second fetch is a no-op after the first; second checkout is a no-op when already on that SHA) and buys the self-healing property. |

### Single-command SSM body via `bash -c`, not a multi-element commands array

| Area | Decision |
|---|---|
| Choice | One string in `{commands: [$cmd]}`, chained with `&&`. Inside that string, one `sudo -u ec2-user bash -c '…'` wraps the pre-guard, then a second `sudo -u ec2-user …/scripts/deploy.sh …` runs the actual deploy. |
| Why | AWS-RunShellScript concatenates multi-element `commands` arrays into one shell invocation without `set -e`; failure of an earlier element doesn't stop later ones. Using `&&` chaining at the top level makes exit semantics unambiguous. `bash -c '…'` for the pre-guard groups the fetch + checkout so `set -e` fails fast inside. jq's `--arg` handles all string quoting, so nested single quotes inside a double-quoted shell string are not a problem here. |

### The one-time bootstrap stays user-run (no scripting)

| Area | Decision |
|---|---|
| Choice | User runs a single `aws ssm send-command …` from the Mac. Not wrapped in a repo script. |
| Why | Per [[feedback-long-running-commands]] and [[feedback-git-operations]] — this is a shared-state mutation on the production box that the user should have eyes on. One-shot bootstrap, no reuse value. If we ever hit this class of chicken-and-egg again, the self-healing guard added this session prevents recurrence, so the script wouldn't be reused anyway. |

---

## Progress

- [x] Session log created (this file).
- [x] `.github/workflows/deploy.yml` — SSM body prepends `git fetch + git checkout $SHA` as ec2-user, chained with `&&` before the `scripts/deploy.sh` invocation.
- [x] `yaml.safe_load` clean on `.github/workflows/deploy.yml`.
- [x] Non-ASCII grep clean on files touched this session.
- [x] Django test suite — no changes; last-green state from S15 (56 tests, ok) still stands. See Digressions for why no new test.
- [ ] User: run the one-time SSM bootstrap command (Section 1 below).
- [ ] User: commit + PR the `deploy.yml` edit → merge → verify next deploy succeeds.
- [x] Session log finalized.

## Digressions worth remembering

**1. Why no new unit test this session.**
The change is entirely in a GitHub Actions workflow file. There is
no Python or JS code surface to add a unit test against — a test
would either need to load the YAML and grep string patterns (a
tautology that would break every time the SSM body evolves) or
actually stand up SSM/EC2 in CI (out of scope). The real
verification is the next successful deploy in the Actions tab.
Per CLAUDE.md tests-before-finalization: this is the "digression
that documents why the test checkbox is n/a" case. If a future
session adds a Python-side deploy helper (e.g. a `scripts/`
Python utility that formats the SSM body), that would be worth
covering with a unit test.

**2. The self-healing guard doesn't paper over a broken deploy SHA.**
The pre-guard does `git checkout --detach $SHA`. If `$SHA` itself
doesn't contain `scripts/deploy.sh` (e.g., someone reverts it
from main and pushes), the guard succeeds but the subsequent
`sudo -u ec2-user …/scripts/deploy.sh …` still fails with
"command not found." That's the correct failure mode — we don't
want the deploy to silently fall back to some other revision's
`deploy.sh`. The guard only fixes the case where the *box's*
checkout is stale, not where the *target SHA* is broken.

---

## User execution checklist

### 1 — One-time SSM bootstrap: git pull the running instance to main HEAD

Run from the Mac after `aws sso login`:

```
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)

command_id=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "S16 bootstrap: git pull to pick up scripts/deploy.sh" \
    --parameters 'commands=["sudo -u ec2-user bash -c \"set -e; cd /home/ec2-user/aws-wedding-website && git fetch --prune origin && git checkout main && git pull --ff-only origin main && ls -la scripts/deploy.sh\""]' \
    --query 'Command.CommandId' --output text)
echo "Dispatched: $command_id"

# Poll until terminal. Success = deploy.sh listed at the end of stdout.
aws ssm wait command-executed \
    --command-id "$command_id" \
    --instance-id "$INSTANCE_ID"

aws ssm get-command-invocation \
    --command-id "$command_id" \
    --instance-id "$INSTANCE_ID" \
    --output json \
  | jq -r '"status: \(.Status)", "----- stdout -----", .StandardOutputContent, "----- stderr -----", .StandardErrorContent'
```

Expected end of stdout:

```
-rwxr-xr-x 1 ec2-user ec2-user <bytes> <date> scripts/deploy.sh
```

### 2 — Commit + merge the `deploy.yml` self-healing edit

This session touched only `.github/workflows/deploy.yml` (plus this
log). The current working branch is `miscellaneous-template-updates`
which has 5 unrelated template commits pending. Recommend one of:

**Option A (cleaner) — separate branch for the deploy fix:**
```
git checkout main
git pull
git checkout -b s16-deploy-bootstrap-fix
git add .github/workflows/deploy.yml .claude/sessions/2026-08-06-session-16-deploy-bootstrap-fix.md
# review with git diff --cached
# commit + push + PR against main
```

**Option B (pragmatic) — fold onto the existing branch:**
```
git checkout miscellaneous-template-updates
git add .github/workflows/deploy.yml .claude/sessions/2026-08-06-session-16-deploy-bootstrap-fix.md
# commit + push + PR against main
```

Either way: when the PR merges to main, the `deploy` workflow will
fire. First it runs the *new* SSM body (pre-guard + deploy.sh
invocation). If the bootstrap in step 1 was already run, the
pre-guard is a no-op on the box (same fetched objects, checkout to
that SHA). If step 1 hadn't been run, the pre-guard would fix the
box itself — that's the self-healing property.

### 3 — Verify the deploy

Actions tab → `deploy` workflow → latest run:
- `python` + `frontend` jobs green.
- `deploy` job → "Trigger SSM RunCommand" step dispatches a command
  id.
- "Wait for deploy.sh to finish + surface output" ends with
  `status: Success` and the tail of stdout showing
  `=== deploy done (…) sha=<merge-sha> http=200 ===`.

Hit `https://kaitlynandsteventietheknot.com` — page loads with the
merged commit's content.

---

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-06-session-16-deploy-bootstrap-fix.md` — this log

**Modified:**
- `.github/workflows/deploy.yml` — SSM RunCommand body now
  prepends `sudo -u ec2-user bash -c 'set -e; cd …; git fetch
  --prune origin; git checkout --detach $SHA'` chained with `&&`
  before invoking `scripts/deploy.sh`.

Per working contract, all `git add` / `git commit` / `git push` is
left to the user ([[feedback-git-operations]]).

## Session 17 handoff

The S15 handoff had five items in "Session 16." This session took
item 0 (bootstrap). The remaining four items carry forward:

### Step 1 — HSTS ramp (assuming Session 15's 60s soak is clean)

If two weeks of green deploys + healthy alarm output have gone by
without any HTTPS regression:

1. `SECURE_HSTS_SECONDS = 3600` — one-hour commitment.
2. `SECURE_HSTS_SECONDS = 604800` — one week.
3. `SECURE_HSTS_SECONDS = 31536000` + `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`.
4. Optionally add `SECURE_HSTS_PRELOAD = True` and submit to
   https://hstspreload.org (irreversible; only once we're 100%
   committed to HTTPS forever on this domain — likely post-wedding).

Each step: settings change + push. Update
`test_hsts_seconds_set_to_soak_value` at each ramp so the test is a
real assertion.

### Step 2 — RDS deletion protection

Flip `aws_db_instance.wedding.deletion_protection` to `true` closer
to the wedding. Non-disruptive `terraform apply`.

### Step 3 — Real gallery page

Session 8's `Gallery` React island against `/api/photos/` is still
stubbed. Design + implement.

### Step 4 — Launch checklist

Draft `.claude/launch-checklist.md` compiling: prod Django
superuser via SSM (S14), SNS confirmation (S15), HSTS verification,
branch protection enforcement, end-to-end deploy verification from
a real push.

### Step 5 — Post-deploy CloudFront invalidation (optional, low priority)

`deploy.sh` doesn't invalidate. Not strictly needed because static
assets are hashed by `ManifestS3StaticStorage` and dynamic pages
are `CachingDisabled` at the CloudFront layer. Only revisit if
caching strategy changes.

## Open questions / follow-ups

*(Carried from Session 15.)*

- Q1 dietary + Q6 schedule — still open from Session 7.
- Photo alt-text values — final copy still pending.
- Deletion protection on RDS — flip closer to the wedding.
- `<picture>` mobile crop for hero — Session 17+.
- `django-vite` — still deferred.
- Real gallery page — Session 17+.
- HSTS full ramp (60 → 31536000, INCLUDE_SUBDOMAINS, PRELOAD,
  submit to hstspreload.org) — Session 17 after soak.
- Unrelated to this session: `miscellaneous-template-updates`
  branch has 5 template commits pending user's own merge decision.
- **Hotel block links — move from home template into the admin
  flow.** User has an unmerged PR that adds hotel-block hyperlinks
  as straight text in the home HTML template. There's already
  Django admin machinery for managing these (likely the same
  Guest/Event-adjacent models we've been using); the correct
  fix is to route the links through that admin surface instead of
  hardcoding them in the template. Revisit before merging that PR
  — probably a small model field addition (or a URLField on an
  existing model) + a template variable swap. Grep for existing
  hotel/venue/accommodation admin logic to find the right seam.
