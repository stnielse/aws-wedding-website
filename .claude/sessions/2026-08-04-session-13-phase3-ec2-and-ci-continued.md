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
- [x] `infra/phase3/ec2.tf` written.
- [x] `infra/phase3/outputs.tf` extended with EC2 outputs.
- [x] `backend/config/settings/production.py` — ALLOWED_HOSTS env-list parsing.
- [x] `backend/config/tests.py` — 3 new ALLOWED_HOSTS tests.
- [x] `pyproject.toml` at repo root written; ruff==0.16.1 pinned in `backend/requirements/local.txt`.
- [x] `ruff check backend/` + `ruff format backend/` — clean. Auto-fix landed I001, UP017, SIM105, F401; hand-fixed 5 E501 line-too-long + 1 E741 (`l` → `label`).
- [x] `.github/workflows/ci.yml` written.
- [x] `terraform validate` + `fmt -diff` + non-ASCII grep — clean. (Non-ASCII grep hit outputs.tf:61 in a Terraform *output* description, not an AWS resource; safe.)
- [x] Full Django test suite passes — 47 tests, ok.
- [x] User ran `terraform apply -replace=aws_instance.web` — succeeded on the 4th attempt after three digressions (see below).
- [x] `curl http://<eip>/` verification — all three ALLOWED_HOSTS values return 200. Actual page (title: `Kaitlyn & Steven · 23 May 2027 · Louland Falls`) rendered from RDS-backed Django + S3-served static.
- [x] Session log finalized.

**End state:** `http://32.199.50.156/` serves the site. Instance
`i-0e86a4994844691a4` in `us-east-1a`, launched
2026-08-04T14:47:41Z (final replace). Terraform state at 40 resources
(Session 11's 18 + Session 12/13's 22).

### Digressions worth remembering

Four failures during the apply/replace loop. Each landed as a fix in
the Session 12 templates and taught us something about the AL2023
runtime.

**1. `corepack: command not found` on AL2023 node20.**
Session 12 assumed `corepack enable` would work on `nodejs20`.
AL2023's `nodejs20` package does not ship a `/usr/bin/corepack` shim.
Fix: `npm install -g pnpm@11.17.0` instead — same result, no
corepack dependency.

**2. `nodejs20` was actually wrong — needed `nodejs22`.**
Session 12's "Node 20 + pnpm 11.17.0 (matches local)" decision was
based on an unverified assumption. `frontend/package.json` pins
`pnpm@11.17.0`, and pnpm 11 requires Node ≥22.13. User's local Node
is 22.23.1. Bumped user_data to `dnf install nodejs22` + pinned
`alternatives --set node /usr/bin/node-22`. Also removed the bare
`npm` package from the dnf install list because it resolves to
`nodejs-npm` (npm for node 18) which drags node 18 in as a dep — and
was masking which node version was actually on `$PATH`.

**3. nginx failed because the sed hack from Session 12 couldn't
handle nested `location{}` blocks.** The regex range
`/^\s*server\s*{/,/^\s*}/` stops at the first `}` at start-of-line,
which is usually a nested location block's closer — leaving the
outer server block's `}` uncommented and the file syntactically
invalid. Fix: overwrite `/etc/nginx/nginx.conf` wholesale with a
minimal main config (`templates/nginx-main.conf.tftpl`) that has no
inline server block, only `include /etc/nginx/conf.d/*.conf`. Our
`wedding-site.conf` provides the only server block. Immune to
future AL2023 formatting drift.

**4. gunicorn socket permission preemptive fix.** After the sed fix
would have landed nginx, the unix socket at `/run/gunicorn/gunicorn.sock`
would have been unreachable by the `nginx` user (default umask →
socket 0755, nginx-user can't write). Added `--umask 007` to
gunicorn args and `usermod -aG ec2-user nginx` in user_data. Bonus:
group creation avoids a 502 that would have cost another apply
cycle.

**5. systemd `EnvironmentFile=` leaves single quotes literal.**
`.env` is generated with jq's `@sh` filter (bash-safe single quotes)
because user_data's own `set -a; . .env; set +a` needs bash quoting
semantics — and DJANGO_SECRET_KEY may contain `$` chars that would
be shell-expanded under double quotes. But AL2023's systemd 252
doesn't strip single quotes from `EnvironmentFile` values, so
`ALLOWED_HOSTS='ip,domain,www.domain'` split on comma inside Django
became `["'ip", "domain", "www.domain'"]`. Middle host worked;
outer two returned `DisallowedHost` 400.

Fix: drop `EnvironmentFile=` from the gunicorn systemd unit.
Instead, user_data creates a wrapper at
`$APP_DIR/scripts/run-gunicorn.sh` that bash-sources `.env` (correct
quote handling), then `exec`s gunicorn. Systemd's ExecStart points
at the wrapper. `.env` stays `@sh`-formatted so both user_data's
own sourcing and the wrapper's sourcing use consistent bash
semantics.

**6. `%{http_code}` in user_data curl format string collided with
Terraform template directives.** `templatefile()` treats `%{...}` as
a control keyword. Escape as `%%{http_code}` so the rendered script
gets the single `%{http_code}`. (Caught by `terraform validate`
before apply — no runtime impact.)

**7. `git clone` in user_data pulls GitHub's `main`, not local
unpushed changes.** Iterated locally on `production.py`'s
ALLOWED_HOSTS parsing but the deployed instance was cloning from
`main` which still had the pre-Session-13 `[os.environ['DOMAIN']]`
version. Django resolved ALLOWED_HOSTS to just `['kaitlynandsteventietheknot.com']`,
which is why *only* the apex host returned 200 even though systemd
had all three in env. Not a code bug — a workflow gotcha. When
iterating on Python code, must push before `apply -replace` for
the change to be visible on the box. This is intentional (the
alternative would be to rsync from laptop, breaking reproducibility)
and Session 15's `deploy.yml` will make the code-shipping step
explicit rather than piggybacking on `git clone`.

---

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-04-session-13-phase3-ec2-and-ci-continued.md` — this log
- `infra/phase3/ec2.tf`
- `infra/phase3/templates/nginx-main.conf.tftpl` (new; digression 3)
- `pyproject.toml` — ruff config
- `.github/workflows/ci.yml`

**Modified:**
- `infra/phase3/outputs.tf` — EC2 outputs
- `infra/phase3/main.tf` — none (already had random provider pin from Session 12)
- `infra/phase3/templates/user_data.sh.tftpl` — digressions 1, 2, 3, 4, 5, 6 (node 22, no npm, wrapper script, nginx main config, umask/group, %% escape)
- `infra/phase3/templates/gunicorn.service.tftpl` — digression 5 (drop EnvironmentFile, ExecStart wrapper)
- `infra/phase3/ec2.tf` — pass `nginx_main` template var
- `backend/config/settings/production.py` — ALLOWED_HOSTS env-list (digression 7)
- `backend/config/tests.py` — 3 ALLOWED_HOSTS tests
- `backend/requirements/local.txt` — pin ruff==0.16.1
- Autoformat pass touched 12 files under `backend/` (ruff format).
- `infra/phase3/.terraform.lock.hcl` — random 3.7.2 added by `terraform init` during validate

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
