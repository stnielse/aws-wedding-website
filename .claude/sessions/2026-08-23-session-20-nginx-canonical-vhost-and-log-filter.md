# Session 20 — nginx canonical vhost + Django 4xx log filter

**Date:** 2026-08-23
**Mode:** Execution — infra template + Django settings
**Model:** Opus 4.7

---

## Context

An ERROR-level burst on 2026-08-21 21:40:54Z paged the
`wedding-site-django-errors` alarm (see `infra/phase3/cloudwatch.tf`).
Root cause: a single scanner sprayed ~250 enterprise-appliance paths
(SAP, Cisco ISE, Confluence, GeoServer, Trend OfficeScan, Zyxel, TP-Link,
ScadaBR, etc.) at the box **directly on the EC2 public hostname**
`ec2-32-199-50-156.compute-1.amazonaws.com:80`, bypassing CloudFront.
Every request arrived at nginx with a Host header outside `ALLOWED_HOSTS`,
so Django raised `django.security.DisallowedHost` at ERROR level — the
metric filter (`{ ($.level = "ERROR") || ($.level = "CRITICAL") }`) matched
each one and the SNS topic fanned them into email.

**Nothing was compromised.** Django's `ALLOWED_HOSTS` correctly refused
every request. The 24-hour-earlier WARNING flood in `django.request` was
the same phenomenon at a different logger — bots probing `/.env`,
`/.git/config`, `/wp-admin/*`, etc. through CloudFront (which forwards the
apex Host, so those reach Django and 404).

Two problems fell out of the investigation:

1. **The alarm fires on scanner traffic** that Django is already refusing —
   a false positive that trains us to ignore future ones (and would
   block the HSTS ramp handoff from S19, which is gated on "ERROR/CRITICAL
   filter staying quiet").
2. **Log volume is dominated by bot 404 WARNINGs**, drowning any real
   signal in CloudWatch.

Both trace back to nginx's `server_name _;` default_server proxying
*everything* to gunicorn regardless of Host header or path pattern.

### Scope explicitly out of this session
- **CloudFront WAF managed rules** — considered, rejected. `$1/mo` + per-request
  costs and per-rule fees for defense that duplicates what nginx-side
  short-circuits give us for free. Revisit only if a wave gets past nginx.
- **Tightening EC2 SG port 80 to CloudFront-only** — real hardening lever
  but nontrivial (AWS-managed prefix list `com.amazonaws.global.cloudfront.origin-facing`
  changes IPs continuously; needs a Lambda or scheduled TF refresh to
  keep the SG rule current). Own session. The nginx 444 catchall in
  this session closes the *behavioral* gap without needing the SG change.
- **Auto-invalidation on Photo save** — still deferred per S19 handoff.

---

## Decisions locked this session

### nginx — split the single `default_server _;` block into canonical vhost + 444 catchall + scanner-pattern shortcuts

| Area | Decision |
|---|---|
| Choice | Rewrite `infra/phase3/templates/nginx-site.conf.tftpl` into three server blocks: (1) `www.${domain_name}` → 301 to apex (unchanged from S18); (2) new canonical `${domain_name}` block that proxies to gunicorn AND contains two `location ~*` regex blocks matching common scanner patterns (dotfiles: `\.env`, `\.git`, `\.aws`, `\.ssh`, `\.htaccess`, `\.htpasswd`; WordPress/PHP: `wp-(admin\|login\|content\|includes\|config\|json)`, `xmlrpc\.php`, `phpmyadmin`, `pma`) that `return 444` with `access_log off`; (3) `server_name _; default_server` that just `return 444;` — no proxy_pass, no logging beyond nginx's own access log. |
| Why | **Why 444 not 404/403.** 444 is nginx's "close TCP connection, no response" signal. Scanners get zero bytes back, gunicorn never wakes, no Django request/response cycle, no CloudWatch log line. 404 would write to the Django `access.log` (which the CloudWatch agent tails per S12+) and still eat gunicorn CPU. **Why a canonical-Host vhost, not a shared `server _;` block with Host validation.** nginx server_name matching is the whole point — the canonical block only picks up requests whose Host is exactly `${domain_name}`, and CloudFront forwards viewer Host verbatim (Managed-AllViewer origin request policy confirmed via `infra/phase3/cloudfront.tf`), so legitimate traffic lands there naturally. Direct-hostname / IP / bogus-Host requests fall through to the default_server 444 — the whole DisallowedHost class of ERRORs goes to zero. **Why regex `location` blocks not `map $request_uri`.** `map` + `if` works but nginx's "if is evil" doc discourages it inside server context; `location ~*` runs before `location /` and is the idiomatic form. **Why two regex blocks not one giant alternation.** Readability. Adding a new pattern is a one-line change to the matching group. **Why `access_log off` on the scanner locations.** The whole point is silencing bot noise; leaving them in the access log defeats the reduction and still gets shipped to CloudWatch. Default_server 444 keeps access_log on — those are rare and worth seeing if something weird pings the origin directly. |

### Django — filter 4xx off `django.request` at the logger level, keep 5xx flowing

| Area | Decision |
|---|---|
| Choice | Add `SkipClient4xx` class to `backend/config/log_formatters.py` — a `logging.Filter` subclass whose `.filter()` returns False for records with `status_code < 500`, True otherwise (including records with no `status_code` attr, so non-request logs routed through a shared handler aren't accidentally muted). In `backend/config/settings/production.py`, add a `filters` section to the `LOGGING` dict and attach `skip_client_4xx` to the `django.request` logger. Level stays WARNING (not bumped to ERROR) so the filter is the sole gate. |
| Why | **Why a filter and not just `level: ERROR`.** Bumping the floor to ERROR would work today (4xx are WARNING, 5xx are ERROR), but couples log level to status semantics in a way that breaks silently if Django's log-level policy ever shifts. The filter says exactly what we mean: "drop 4xx, keep 5xx." Grep-able intent. **Why filter attr `status_code` not the exception type.** Django populates `record.status_code` uniformly on the `django.request` logger for both `Resolver404` and other client errors; the exception attr isn't always present. `status_code` is the stable API. **Why return True when `status_code` is missing.** Defense-in-depth: if a future change routes non-request logs through the same handler (e.g. a shared filter on the root logger), we don't want to silently swallow them. **Why not touch `django.security.DisallowedHost`.** After the nginx canonical-vhost change, that logger fires ~zero times per day — no filter needed. If it ever fires post-cutover, we want to see it, because it means either (a) CloudFront's Host-forwarding behavior changed, or (b) `ALLOWED_HOSTS` and the nginx `server_name` drifted apart. Both are real signal. |

### Rollout path — reuse the S19 nginx-sync in `scripts/deploy.sh`; no manual SSM needed

| Area | Decision |
|---|---|
| Choice | S19 added `scripts/wedding-nginx-sync.sh` + wired it into `scripts/deploy.sh` (envsubst render → diff → sudo-invoke sync helper → `nginx -t` + reload with rollback). This session's nginx template change ships through that path automatically on the next merge to main — deploy.sh will `cmp -s` the rendered new config against `/etc/nginx/conf.d/wedding-site.conf`, see the diff, and run the sync. Django settings change ships the same way (existing systemd unit picks up the new `LOGGING` after gunicorn restart). No manual SSM `send-command` this session. |
| Why | S19 explicitly closed the "nginx template change requires manual SSM apply" workflow gap; this session is the first real test of that. If the deploy path works, the workflow investment from S19 pays off. If it doesn't, that's a load-bearing bug in `deploy.sh` we want to fix once and reuse forever, not paper over with per-session manual SSM. |

---

## Progress

- [x] Session log created (this file).
- [x] `infra/phase3/templates/nginx-site.conf.tftpl` — rewritten: canonical vhost, scanner-pattern location blocks, default_server 444.
- [x] `backend/config/log_formatters.py` — `SkipClient4xx` filter class appended.
- [x] `backend/config/settings/production.py` — `LOGGING['filters']` section added; filter attached to `django.request`.
- [x] Unit tests — `SkipClient4xxTests` (5 cases: drops 404, drops all 4xx incl. 400/401/403/418/429/499, keeps 5xx, boundary at 500, keeps records with no `status_code` attr) + `ProductionLoggingWiringTests` (3 cases: filter registered in `LOGGING['filters']`, attached to `django.request`, level stays WARNING). 75/75 passing including the pre-existing 67.
- [ ] Local smoke: `envsubst '${domain_name}' < infra/phase3/templates/nginx-site.conf.tftpl` renders cleanly with `$host`/`$request_uri`/`$scheme` preserved; `nginx -t -c /tmp/rendered.conf` in a container/VM validates syntax.
- [ ] Deploy to prod via merge to main; watch `/wedding-site/django` for the DisallowedHost ERROR count to drop to zero over the following 24h.
- [ ] Handoff update: HSTS ramp (S19 open item) unblocks once the ERROR count stays quiet for the S15 soak window.

---

## Files modified this session

- `infra/phase3/templates/nginx-site.conf.tftpl` — full rewrite (see decision 1).
- `backend/config/log_formatters.py` — appended `SkipClient4xx` class.
- `backend/config/settings/production.py` — `LOGGING` dict grew `filters` section; `django.request` logger gained `filters: ['skip_client_4xx']`.
- `backend/config/tests.py` — new `SkipClient4xxTests` (filter behavior) and `ProductionLoggingWiringTests` (LOGGING dict wiring) classes; import of `SkipClient4xx` alongside `JsonFormatter`.

---

## Verification plan

Post-deploy, from a machine outside the VPC:

```bash
# 1) Wrong-Host direct-to-EC2 hits: should hang / connection-closed (444).
#    Resolve the EC2 hostname via terraform output rather than typing it in.
EC2_HOST=$(terraform -chdir=infra/phase3 output -raw ec2_public_dns)
curl -v --max-time 5 "http://${EC2_HOST}/" || echo "expected: empty reply / connection reset"

# 2) Scanner path via canonical Host: 444 close, no Django log line.
curl -v --max-time 5 -H "Host: kaitlynandsteventietheknot.com" "http://${EC2_HOST}/.env"
curl -v --max-time 5 -H "Host: kaitlynandsteventietheknot.com" "http://${EC2_HOST}/wp-admin/install.php"

# 3) Legit path via canonical Host: 200.
curl -v --max-time 10 -H "Host: kaitlynandsteventietheknot.com" "http://${EC2_HOST}/"

# 4) End-to-end via public URL: nothing should change for real viewers.
curl -sI "https://kaitlynandsteventietheknot.com/" | grep -E '^HTTP|^x-cache'
```

CloudWatch check (24h after deploy):
- `django.security.DisallowedHost` count in `/wedding-site/django` → expect 0.
- `django.request` WARNING count → expect large drop.
- `django-errors` alarm state → expect `OK`, no state transitions.

---

## Open questions / follow-ups

*(Carrying S19 handoff plus new items.)*

- **NEW — Watch for a scanner wave that patterns past our regex list.**
  The `location ~*` blocks are a starting set (dotfiles + WP/PHP). New
  patterns showing up in the log group after deploy are one-line additions
  to the template. Not worth pre-emptively adding hundreds of patterns —
  405 unique paths in the 08-21 burst but the ones that repeat across
  waves are what pay off to block.
- **NEW — EC2 SG port 80 → CloudFront-only.** True hardening step that
  makes the nginx 444 catchall belt-and-suspenders rather than sole
  defense. Needs prefix-list plumbing; own session. See Scope-out above.
- **NEW — CloudFront WAF managed rules.** Consider only if a scanner
  wave gets past nginx and touches Django in a way that matters. Rejected
  this session on cost/value grounds.
- **HSTS ramp** — S19 gated this on the ERROR/CRITICAL filter staying quiet;
  the 08-21 burst reset that clock. Reopens after this session's fix
  soaks for the same window (a few clean days).
- **RDS deletion protection** — flip 2027-01/02.
- **Auto-invalidation on Photo save** — deferred from S19.
- **Photo alt-text / captions** — admin follow-up.
- **`<picture>` mobile crop for hero** — carried from S15.
- **`django-vite`** — deferred, not blocking.
- **Remove/narrow cloud-init's `(ALL) NOPASSWD: ALL` grant to ec2-user**
  — carried from S19 (S19 Digression 3).
