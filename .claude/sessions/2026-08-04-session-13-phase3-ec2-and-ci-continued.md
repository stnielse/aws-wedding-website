# Session 13 — Phase 3 tail (continued): EC2 + first deploy + CI workflow

**Date:** 2026-08-04
**Mode:** Execution — finish Session 12's Phase 3 tail
**Model:** Opus 4.7

---

## Context

Session 12 (`2026-08-02-session-12-phase3-ec2-and-ci.md`) ran up against
the credit-usage cap before finishing. All the SSM + IAM + SG +
templates work landed and was committed (see `git log` — 14 commits
ending at `2843054 session 12 log update for credit usage cap`), but
`ec2.tf`, `outputs.tf` extension, `production.py` ALLOWED_HOSTS
parsing, `pyproject.toml`, ruff install/run, `.github/workflows/ci.yml`,
`terraform validate`, tests, and the `plan`/`apply` handoff were all
deferred. Session 12's PICKUP block is the authoritative task list for
today.

**Renumber note.** Session 12's forward plan referred to
"Session 13 = CloudFront cutover, Session 14 = CloudWatch + deploy."
That plan slides by one: today's log absorbs the Session 12 tail, so
CloudFront becomes **Session 14** and CloudWatch + deploy becomes
**Session 15**. All decisions, out-of-scope items, and open questions
from the Session 12 log carry forward unchanged unless explicitly
overridden below.

**No AWS state has changed since Session 11's apply** — Terraform state
is still at 18 resources (VPC + subnets + IGW + RTs + SGs + RDS +
subnet group + log group + parameter group). Today's apply lands
everything in Session 12's plan and this session's `ec2.tf`.

## Session plan

Executes Session 12's PICKUP list top-to-bottom. Numbered here for
progress tracking; content is the same:

1. Create this session log (in progress).
2. Write `infra/phase3/ec2.tf` per Session 12's PICKUP block.
3. Extend `infra/phase3/outputs.tf` with EC2 outputs.
4. Update `backend/config/settings/production.py` for comma-separated
   `ALLOWED_HOSTS`; add test in `backend/config/tests.py`.
5. Create `pyproject.toml` at repo root with `[tool.ruff]` config; pin
   `ruff` exact-version in `backend/requirements/local.txt`.
6. `.venv/bin/pip install -r backend/requirements/local.txt` (picks up
   ruff), then `ruff check backend/` + `ruff format backend/`. Fix real
   issues; leave the formatting fixes for the user to commit.
7. Write `.github/workflows/ci.yml` — parallel `python` + `frontend`
   jobs; triggers `push` (any branch) + `pull_request`.
8. `terraform -chdir=infra/phase3 validate` + `fmt -diff` + non-ASCII
   grep (per [[feedback-aws-ascii-only-descriptions]]).
9. `.venv/bin/python manage.py test` from `backend/` — expect ≥45 tests
   pass, including the new ALLOWED_HOSTS test.
10. Hand `terraform plan -out=tfplan` + `apply tfplan` to the user
    ([[feedback-long-running-commands]]). Expected ~22 new resources.
11. Once EIP is live, `curl -sI` verify site responds. Finalize this
    log.

---

## Decisions locked this session

*(Session 12's locked decisions carry over unchanged. Only new
decisions or refinements below.)*

### Session renumbering absorbed here, not deferred

| Area | Decision |
|---|---|
| Choice | Today's log picks up Session 12's tail rather than starting fresh work; CloudFront becomes Session 14, CloudWatch+deploy becomes Session 15. |
| Why | Session 12's tail is a coherent unit — CI + first deploy on EIP — and splitting it across "Session 12 remnants" + "Session 13 real work" would fragment the handoff. Renumbering downstream sessions once is cheaper than carrying "Session 12 pt.2" nomenclature forward. |

### `pnpm lint` = `oxlint` (already pinned)

| Area | Decision |
|---|---|
| Choice | CI's `frontend` job just calls `pnpm lint`, which resolves to `oxlint` per `frontend/package.json`. No new linter to pick. |
| Why | Session 6 already picked oxlint over eslint (faster, zero-config, TS-aware). CI just needs to call it. |

### Ruff version pin

| Area | Decision |
|---|---|
| Choice | `ruff==0.14.4` (latest at time of writing per Session 12's PICKUP note). Pinned in `backend/requirements/local.txt`. |
| Why | Strict version pins per [[feedback-strict-version-pins]]. Ruff bumps aggressively and rule outputs can shift between minor versions — pin so CI + local always agree. |

### ALLOWED_HOSTS parsing

| Area | Decision |
|---|---|
| Choice | `os.environ.get('ALLOWED_HOSTS', os.environ['DOMAIN']).split(',')`, strip + drop empties. Test lives in `backend/config/tests.py` alongside the existing storage + logging tests (`SimpleTestCase`, no DB needed). |
| Why | Small logic, single test file; no need for a new module. Falling back to DOMAIN keeps local `manage.py runserver --settings=config.settings.production` viable if we ever try it. |

---

## Progress

- [x] Session log created (this file).
- [ ] `infra/phase3/ec2.tf` written.
- [ ] `infra/phase3/outputs.tf` extended with EC2 outputs.
- [ ] `backend/config/settings/production.py` — ALLOWED_HOSTS env-list parsing.
- [ ] `backend/config/tests.py` — new ALLOWED_HOSTS test.
- [ ] `pyproject.toml` at repo root written; ruff pinned in `backend/requirements/local.txt`.
- [ ] `ruff check backend/` + `ruff format backend/` — clean.
- [ ] `.github/workflows/ci.yml` written.
- [ ] `terraform validate` + `fmt -diff` + non-ASCII grep — clean.
- [ ] Full Django test suite passes (≥45 tests).
- [ ] User runs `terraform plan -out=tfplan` + `apply` — pending.
- [ ] `curl http://<eip>/` verification — pending.
- [ ] Session log finalized — pending.

### Digressions worth remembering

*(Filled during execution.)*

---

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-04-session-13-phase3-ec2-and-ci-continued.md` — this log
- `infra/phase3/ec2.tf`
- `pyproject.toml` — ruff config
- `.github/workflows/ci.yml`

**Modified:**
- `infra/phase3/outputs.tf` — EC2 outputs
- `backend/config/settings/production.py` — ALLOWED_HOSTS env-list
- `backend/config/tests.py` — ALLOWED_HOSTS test
- `backend/requirements/local.txt` — pin ruff

Per working contract, all `git add` / `git commit` is left to the user.

## Session 14 handoff

Session 14 is Session 12's originally planned "Session 13" (CloudFront
+ DNS cutover + phase 0 destroy + branch protection). The prep list
from Session 12's "Session 13 handoff" section applies verbatim —
consult that block when Session 14 starts. Do not re-derive; it's a
complete plan.

## Open questions / follow-ups

*(Carried from Session 12 unchanged.)*

- Q1 dietary + Q6 schedule — still open from Session 7.
- Photo alt-text values — final copy still pending.
- Deletion protection on RDS — flip closer to the wedding.
- `<picture>` mobile crop for hero — Session 14+.
- `django-vite` — still deferred.
- Real gallery page — Session 14+.
- Frontend build on EC2 vs CI-shipped artifacts — Session 15 (deploy
  workflow) may switch to CI-build-then-rsync.
- `SECURE_HSTS_*` — Session 14 or hardening pass.
