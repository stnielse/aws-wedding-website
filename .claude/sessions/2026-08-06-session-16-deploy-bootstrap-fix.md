# Session 16 — Deploy bootstrap fix + launch checklist + phase3 README RDS note

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
covered five items (bootstrap, HSTS ramp, RDS deletion
protection, real gallery, launch checklist). After running the
bootstrap and confirming success mid-session, user asked to
"knock out the rest." Scope actually landed this session:

- **Bootstrap fix + self-healing guard** (Step 0) — done.
- **Launch checklist** (Step 4) — done, drafted at
  `.claude/launch-checklist.md`.
- **CloudFront invalidation** (Step 5) — consciously skipped with
  the reasoning documented in this log and in the launch
  checklist "Notes" section.
- **RDS deletion protection** (Step 2) — decision explicitly
  documented in `infra/phase3/README.md` with the "when to flip"
  criterion and the plan/apply commands; the actual flip is
  deferred to ~T–3 to T–4 months (2027-01/02).
- **HSTS ramp** (Step 1) — deferred to S17+. S15's plan asked for
  2 weeks of 60s soak; we've had 1 day. Doing the ramp now
  defeats the soak's purpose.
- **Real gallery page** (Step 3) — deferred to S17+. Design +
  build, worth its own session with a design pass on the photo
  grid + lightbox behavior.

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

### CloudFront invalidation deliberately not added to deploy.sh

| Area | Decision |
|---|---|
| Choice | `scripts/deploy.sh` does *not* fire `aws cloudfront create-invalidation` after `collectstatic`. Deploy stays: pip install → tar extract → migrate → collectstatic → restart gunicorn → curl-probe. No CloudFront call. |
| Why | Given the current cache config, no invalidation is needed: (1) **Default behavior (`/*`, Django HTML pages)** uses the AWS-managed `CachingDisabled` cache policy — every request forwards to the EC2 origin. There is no cache to invalidate. (2) **`/static/*`** uses `CachingOptimized`, but Django's `ManifestS3StaticStorage` hashes filenames on `collectstatic`. A changed asset produces a new hashed URL; templates reference the new URL; CloudFront cannot serve stale content because nothing is asking for it. Old hashed URLs remain cached but are never requested. (3) **`/media/*`** uses `CachingOptimized` on uploads, and media object keys are content-URI-stable — we don't overwrite in place. Only case that would require an invalidation: someone manually overwrites a media object at the same S3 key with different content, or we change the default-behavior cache policy to actually cache Django-rendered pages. Neither is planned. Documented in the launch checklist "Notes" section so future-me doesn't add the invalidation step "just in case." |

### RDS deletion protection stays `false` today; decision documented in phase3 README

| Area | Decision |
|---|---|
| Choice | `aws_db_instance.wedding.deletion_protection = false` unchanged this session. Added a dedicated "RDS deletion protection — deferred flip" section to `infra/phase3/README.md` explaining the current-state rationale (destroy stays clean during build), the flip criterion (no more expected phase 3 tear-downs, roughly T–3 to T–4 months from the wedding = 2027-01/02), and the exact plan/apply commands to flip or un-flip. The launch checklist's "Security posture" section requires `deletion_protection = true` before the T–8-weeks verification pass, so the flip lands well before launch. |
| Why | User's specific ask: document the decision explicitly in phase3's README so the "why is this off" question has a durable answer in the module's own docs, not just in a session log that's harder to find. Session logs are the *why-we-decided* record; the README is the *what-the-current-state-is-and-when-to-change* record. Both exist. |

### Launch checklist lives at `.claude/launch-checklist.md`, structured T–8 weeks + T–1 week

| Area | Decision |
|---|---|
| Choice | Single markdown file, nine numbered sections (prereqs, access + admin, deploy pipeline, security posture, observability, backups + recovery, content readiness, DNS + reachability, cost + surprise-services check, post-launch cleanup). Every step has an exact command or click-path — no derivation required at launch time. Two-wave structure: T–8 weeks (2027-03-28) for first pass with buffer for red-item fixes; T–1 week (2027-05-16) for final content freeze + manual RDS snapshot. |
| Why | Wedding launches are one-shot; the checklist is only useful if it's runnable without thinking. The T–8-week wave catches infra issues with time to fix. The T–1-week wave catches content drift (copy tweaks, photo swaps, hotel block URL changes) without giving those changes time to introduce their own regressions. Scope is intentionally focused on things that actually matter for this site (~50 guests, private audience, read-heavy): no load testing, no pen testing, no WAF. Called out as out-of-scope in the "Notes" section so the omission is deliberate, not forgotten. |

---

## Progress

- [x] Session log created (this file).
- [x] `.github/workflows/deploy.yml` — SSM body prepends `git fetch + git checkout $SHA` as ec2-user, chained with `&&` before the `scripts/deploy.sh` invocation.
- [x] `yaml.safe_load` clean on `.github/workflows/deploy.yml`.
- [x] Non-ASCII grep clean on files touched this session (matches only in prose; no AWS-resource description surface).
- [x] Django test suite — no changes; last-green state from S15 (56 tests, ok) still stands. See Digressions for why no new test.
- [x] User: ran the one-time SSM bootstrap command mid-session. `scripts/deploy.sh` now present on the box.
- [x] `.claude/launch-checklist.md` — drafted, nine sections, two-wave structure (T–8 weeks + T–1 week).
- [x] `infra/phase3/README.md` — added "RDS deletion protection — deferred flip" section documenting current state, flip criterion, and plan/apply commands.
- [x] User: merged S16 PR (`session-16` → main, SHA `5b7bb2e`) — deploy workflow fired, self-healing guard worked (fetch + checkout `5b7bb2e` on the box), pip/tar/migrate/collectstatic/gunicorn-restart all succeeded, **but** post-flight probe returned HTTP 400 → deploy step failed. See Digression 3.
- [x] `scripts/deploy.sh` — fixed the post-flight probe: added `-H "Host: $DOMAIN"` to the localhost curl so Django's `ALLOWED_HOSTS` doesn't 400 it.
- [x] User: pushed the deploy.sh fix straight to main via the `stnielse` ruleset bypass; deploy workflow succeeded end-to-end. Automated pipeline confirmed operational.
- [x] Deleted unused `HotelBlock` model — removed the class from `backend/pages/models.py`, removed the import + `admin.site.register` from `backend/pages/admin.py`, generated `backend/pages/migrations/0002_drop_hotelblock.py` (one `DeleteModel` op). Resolves the S16-backlog "hotel block links" item by way of: model was built speculatively in an earlier phase, never wired to a view, template renders inline HTML that fits the design better than a model loop would. Inline HTML in `home.html` stays. Test suite: 56 tests, still green.
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

**3. Latent S15 bug: post-flight probe hit `ALLOWED_HOSTS` 400.**
S16's PR (`session-16` → main, SHA `5b7bb2e`) triggered the very
first end-to-end automated deploy where the post-flight check
actually ran. It failed. `scripts/deploy.sh:82` was:

```
status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/)
```

`curl http://localhost/` sends `Host: localhost`. Django's
`CommonMiddleware` runs the `ALLOWED_HOSTS` check before anything
else — including `SecurityMiddleware`'s SSL-redirect logic —
and the box's `ALLOWED_HOSTS` env is
`32.199.50.156,kaitlynandsteventietheknot.com,www.kaitlynandsteventietheknot.com`
(no `localhost`). So Django returned 400 (`DisallowedHost`), the
case block matched the wildcard, deploy.sh exited 1, and the
workflow failed.

Real user traffic was fine throughout — CloudFront's `AllViewer`
origin request policy forwards the viewer's Host header
(`kaitlynandsteventietheknot.com`) to gunicorn, which passes the
allow-hosts check. Only the localhost probe was broken. The site
never went down; the deploy job just told CI "no."

**Fix** — the smallest possible: pass a Host header curl.
`$DOMAIN` is already sourced from `backend/.env` earlier in the
script (`set -a; . .env; set +a`), so no new inputs needed.

```
status=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $DOMAIN" http://localhost/)
```

Landed in this session. Note: this was written into `deploy.sh`
in Session 15 and never exercised there (the S15 deploy failed
one step earlier at "command not found" per Digression 3 above,
so the probe never ran). Lesson: any step guarded by a preceding
step that itself has known-failing preconditions is functionally
untested until the earlier step is fixed. When we added
`scripts/deploy.sh` in S15, the whole "downstream post-flight"
was implicitly a first-run risk. Worth calling out in future
sessions: if you're writing a new script whose steps depend on
things a not-yet-run pipeline will produce, mentally flag each
step as "not yet exercised" and treat the first successful run
as a diagnostic exercise, not just a green light.

**3b. Why the probe uses `-H "Host: $DOMAIN"` rather than
`curl http://$DOMAIN/`.** Two reasons: (1) resolving the apex
domain from the box would go through the public DNS → CloudFront
→ back to the EC2 origin — a slow, indirect probe that doesn't
actually test the local gunicorn/nginx stack. (2) The bug we
just hit is precisely the one where the app's Host validation
matters — so overriding the header while pointing at localhost
is the correct test: it exercises the exact code path Django
runs for real traffic, without leaving the box.

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

### 2 — Commit + merge this session's changes (S16 PR — DONE)

S16's initial changes were bundled into `session-16` and merged
as PR #3 (SHA `5b7bb2e`). Deploy workflow fired, self-healing
guard worked as designed, but the post-flight probe failed with
HTTP 400 — see Digression 3. Site itself stayed up; only the
deploy job's post-flight check failed.

### 2b — Hot-fix PR: deploy.sh post-flight Host header

One file changed (`scripts/deploy.sh`), plus this session log
extension. Recommend a small standalone PR — it's a real
production-path fix and shouldn't be batched with unrelated
template edits:

```
git checkout main
git pull
git checkout -b s16-deploy-postflight-host-header
git add scripts/deploy.sh \
  .claude/sessions/2026-08-06-session-16-deploy-bootstrap-fix.md
# review with git diff --cached
# commit + push + PR against main
```

When the PR merges, the deploy workflow fires. The new SSM guard
`git checkout --detach $SHA` picks up the fixed `deploy.sh`
before running it, so the fix takes effect on its own merge.
No manual bootstrap needed this time.

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
- `.claude/sessions/2026-08-06-session-16-deploy-bootstrap-fix.md` — this log.
- `.claude/launch-checklist.md` — pre-wedding verification checklist, two-wave (T–8 weeks + T–1 week).

**Modified:**
- `.github/workflows/deploy.yml` — SSM RunCommand body now
  prepends `sudo -u ec2-user bash -c 'set -e; cd …; git fetch
  --prune origin; git checkout --detach $SHA'` chained with `&&`
  before invoking `scripts/deploy.sh`.
- `infra/phase3/README.md` — added "RDS deletion protection —
  deferred flip (decision)" section between the RDS verification
  section and Teardown; updated Teardown's existing brief mention
  to cross-reference.
- `scripts/deploy.sh` — post-flight probe now sets
  `-H "Host: $DOMAIN"` on the curl so Django's ALLOWED_HOSTS
  check doesn't 400 the localhost probe. Fix for latent S15 bug
  surfaced by the S16 PR merge (see Digression 3).

Per working contract, all `git add` / `git commit` / `git push` is
left to the user ([[feedback-git-operations]]).

## Session 17 handoff

The S15 handoff had five items in "Session 16." S16 landed
bootstrap + launch checklist + CloudFront no-op documentation +
RDS decision doc. Two items carry forward, both timing-gated:

### Step 1 — HSTS ramp (timing gate: soak must be clean)

**Gate:** at least two weeks of green deploys + zero HTTPS-related
alarm output from Session 15's ERROR/CRITICAL metric filter. S15
was 2026-08-05, so the earliest this can start is ~2026-08-19,
and only if the alarm has stayed quiet.

Ramp sequence (one step per session, verify pin in browser DevTools
after each push):

1. `SECURE_HSTS_SECONDS = 3600` — one-hour commitment.
2. `SECURE_HSTS_SECONDS = 604800` — one week.
3. `SECURE_HSTS_SECONDS = 31536000` + `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`.
4. Optionally add `SECURE_HSTS_PRELOAD = True` and submit to
   https://hstspreload.org (irreversible; only once we're 100%
   committed to HTTPS forever on this domain — likely post-wedding).

Each step: settings change + push (deploy workflow handles the
rest). Update `test_hsts_seconds_set_to_soak_value` in
`backend/config/tests.py` at each ramp so the test is a real
assertion of the current pin, not a rubber stamp.

### Step 3 — Real gallery page

Session 8's `Gallery` React island against `/api/photos/` is still
stubbed. Deserves its own session with a design pass first:

- Photo grid layout (masonry? uniform? aspect-preserving?).
- Lightbox / detail view behavior (keyboard nav, close-on-swipe).
- Image loading strategy (lazy load, `loading="lazy"`, `<picture>`
  with mobile crops per S15's carried-over follow-up).
- Alt-text sourcing (from admin, not hardcoded — pairs with the
  S15 open question and the S16 hotel-block-links backlog item).

### Timing-gated but not "carry forward" — RDS deletion protection

Not a session task; a calendar item. Flip
`aws_db_instance.wedding.deletion_protection` to `true` around
T–3 to T–4 months (2027-01/02), per the criterion documented in
`infra/phase3/README.md`. The launch checklist section 3
enforces it before the T–8-week verification pass.

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
