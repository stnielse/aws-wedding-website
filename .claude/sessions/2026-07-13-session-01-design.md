# Session 01 — Design Consolidation

**Date:** 2026-07-13
**Mode:** Discussion / design only (no source code written)
**Model:** Opus 4.7, xhigh effort

---

## Context

The user is a professional software engineer building their own wedding website on AWS
for privacy, data ownership, and resume-relevant AWS experience. Target: live and
stable by end of June 2026. AWS foundations (account, IAM admin, budget, ACM cert,
Route 53 hosted zone) are already provisioned. The repo currently contains only
handoff docs — no application code yet. This session is intentionally **discussion /
design first, no code** — the goal is to reconcile ambiguities in the handoff, agree
on scope, and set up the next session for productive implementation.

Repo: `github.com/stnielse/aws-wedding-website` (remote already configured).

---

## Decisions locked this session

| Area | Decision |
|---|---|
| Session 1 mode | Design / discussion only — no source code written yet |
| EC2 OS | **Amazon Linux 2023** (dnf, `ec2-user`) — rewrites the apt/ubuntu snippet in the handoff |
| Site access gate | **Shared wedding code** for site entry (session cookie), separate per-guest `lookup_code` for RSVP page |
| Honeymoon fund payment integration | **Deferred** — stub "coming soon" page in Phase 2, real Venmo/PayPal only if Phase 6 has runway |
| S3 in local dev | Provision the media bucket early; use real S3 from dev too (catches django-storages + IAM bugs sooner) |
| RSVP rate limiting | `django-ratelimit` decorator on the submission view (in-memory cache) |
| Custom subagents to build | `cost-guard`, `wedding-copy-editor` |
| **Git operations** | **Claude never stages, commits, or pushes.** All `git add`, `git commit`, `git push` (and force-push, tag, branch delete, etc.) are performed by the user. Claude may propose commit messages and describe what's staged, but never runs the commands. |
| Session logs | Every session's decisions + progress get their own dated file under `.claude/sessions/`. |

---

## Handoff issues resolved

1. **AL2023 vs Ubuntu mismatch.** Handoff line 52 said Amazon Linux 2023 but the EC2
   setup section uses `apt` and `/home/ubuntu`. Locked on AL2023; the setup script
   will be rewritten to use `dnf` and `/home/ec2-user`. Handoff will be edited to
   match when we start Phase 4.
2. **"Sign-in code" ambiguity.** Handoff mentioned blocking public access with a code
   but the only model with a code was `Guest.lookup_code` (which is also the RSVP
   lookup). Resolved: shared code for site entry + guest `lookup_code` for RSVP. A
   `SiteAccessMiddleware` will short-circuit any unauthenticated request that hasn't
   set the `site_access_ok` session flag by submitting the shared code.
3. **Payment integration scope creep.** Handoff phrased it as "possible." Cut from
   the critical path — stub page only, real integration is a Phase 6 stretch goal.

---

## Open design decisions (need input in Session 2)

- **Phase 0 hosting.** Two viable ways to ship a maintenance page:
  - **A. S3 static website + CloudFront + Route 53 alias**, using the existing ACM
    cert. Costs pennies; the CloudFront distribution gets reused in Phase 4 (add EC2
    as an origin, keep S3 as the `/media/*` origin). Recommended.
  - **B. Manual index.html on a t3.micro** — worst of both worlds, EC2 running from
    day 1 with nothing to serve.
- **Phase 0 IaC or console click-through.** The rest of the project is strict
  Terraform. Phase 0 could be a small `phase0.tf` that we later fold into
  `cloudfront.tf` / `s3.tf`, or a one-off console setup we recreate in Terraform
  when we get to Phase 3. Recommendation: minimal Terraform module now so
  `terraform destroy` still works.
- **Shared wedding code — where does it live?** Options: Django setting from `.env`
  (simplest, requires a redeploy to rotate), or a `SiteAccessCode` singleton model
  editable in admin (rotatable without deploy, small extra schema). Recommend the
  model — the couple can rotate it if it leaks.
- **Photo intake workflow.** Handoff assumes admin upload only. For "lots of
  photos," that means a lot of admin clicking. Worth discussing: a management
  command (`manage.py import_photos <dir>`) that batch-uploads a directory to S3
  and creates `Photo` rows.

---

## Recommended Session 2 scope: Phase 0

Ship the maintenance page so the domain resolves. Concrete deliverables:

- `infra/phase0/` Terraform module:
  - Private S3 bucket for maintenance HTML (OAC-restricted)
  - CloudFront distribution with the ACM cert (us-east-1) attached, default root
    object `index.html`, custom error responses returning 200 with the maintenance
    page for 403/404 so *every* path shows the same "under construction" message
  - Route 53 A-record alias at the apex + `www` → CloudFront
- A single `index.html` with tasteful maintenance copy (no framework, no assets
  beyond inline CSS)
- **Explicit teardown test** — after `terraform apply` succeeds and DNS propagates,
  run `terraform destroy` in a scratch workspace and confirm zero orphaned
  resources. This validates the teardown discipline we'll rely on post-wedding.

Verification for Session 2:
- `curl -I https://<domain>` returns 200 with a CloudFront `via` header
- Browser shows the maintenance page from both apex and `www`
- HTTP requests 301 to HTTPS
- `terraform destroy` leaves the account with only pre-existing resources (hosted
  zone, ACM cert, budget, IAM users)

---

## Custom subagents to build (Session 2 or 3)

Both live under `.claude/agents/` in this repo (project-scoped, not user-scoped) so
they travel with the project and any collaborator gets them for free.

### `cost-guard`
- **Trigger:** Whenever an infra diff touches `infra/**/*.tf` or the user asks to
  review AWS cost implications.
- **Tools:** Read, Bash (read-only: `terraform plan`, `aws pricing`, `aws ce`), Grep.
- **Job:** Scan the Terraform diff and flag anything that:
  - Creates ongoing-billing resources not already in the plan (NAT gateways, ALBs,
    EIPs, RDS instances, extra CloudFront distributions)
  - Increases instance size / storage
  - Creates CloudWatch log groups without a `retention_in_days`
  - Enables AWS services with free-trial-then-bill behavior (GuardDuty, Inspector,
    Security Hub, Macie — the ones the handoff already blacklists)
  - Uses `force_destroy = false` on S3 buckets we intend to tear down
- **Output:** Bullet list, most-costly first, with monthly-cost estimate and a
  one-line fix for each. Empty output if the diff is cost-neutral.

### `wedding-copy-editor`
- **Trigger:** User-facing copy edits — FAQ answers, hotel page, registry blurbs,
  RSVP confirmation email, error strings.
- **Tools:** Read, Edit, Grep.
- **Job:** Voice/tone consistency (warm, second-person, no corporate hedging),
  grammar, guest-facing clarity (no jargon, no dev language), consistent naming
  of the couple and venue.
- **Output:** Suggested rewrites shown inline with rationale; user approves before
  Edit applies.

---

## Files critical to the eventual build (for reference; nothing to touch yet)

- `.claude/wedding-site-handoff.md` — source of truth for scope and structure
- `backend/config/settings/{base,local,production}.py` — settings split
- `backend/rsvp/models.py`, `backend/gallery/models.py`, `backend/pages/models.py`
- `backend/rsvp/views.py` — the `django-ratelimit`-decorated JSON endpoint
- `frontend/src/{RsvpForm.jsx,Gallery.jsx,main.jsx}` — the only two React islands
- `infra/*.tf` — Terraform for every AWS resource; the teardown-clean requirement
  is load-bearing
- `.github/workflows/deploy.yml` — OIDC-federated deploy via SSM `send-command`

---

## Persistence tasks on exit from plan mode

Immediately after `ExitPlanMode` approval, before any implementation:

1. Save a **feedback memory** capturing the "Claude never runs git write ops" rule
   with the reason (user owns all commit history) and how to apply (skip
   staging/commit/push in all workflows, PR flows, and slash commands; propose
   messages only).
2. Save a **feedback memory** capturing the "session log per session under
   `.claude/sessions/`" workflow so future sessions start by creating their own
   log file.
3. Create `CLAUDE.md` in the repo root recording both rules under a "Working
   contract" section so the constraints travel with the project and load into
   every future session's context automatically.

---

## Session 1 progress

- ✅ Read `.claude/wedding-site-handoff.md` and `.claude/pre-claude-setup.md`
- ✅ Confirmed repo state (docs only, remote configured, no source code)
- ✅ Resolved 3 handoff ambiguities via clarifying questions
- ✅ Committed to 2 custom subagents (`cost-guard`, `wedding-copy-editor`)
- ✅ Locked working-contract rule: Claude never runs git write ops
- ✅ Locked working-contract rule: every session gets a dated `.claude/sessions/` log
- ✅ Saved feedback memory: `feedback_git_operations.md`
- ✅ Saved feedback memory: `feedback_session_logs.md`
- ✅ Created repo-root `CLAUDE.md` with the working contract
- ⏭ **Next:** Session 2 — Phase 0 maintenance page (S3 + CloudFront + Route 53 alias
  via a `infra/phase0/` Terraform module)

## Files created / modified this session

- `.claude/sessions/2026-07-13-session-01-design.md` — this file
- `CLAUDE.md` — repo-root working contract

(Memory files live outside the repo at
`~/.claude/projects/-Users-stevennielsen-aws-wedding-website/memory/` and are not
tracked in git.)
