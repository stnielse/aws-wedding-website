# Session 21 — EC2 SG port 80 → CloudFront-only lockdown

**Date:** 2026-11-18
**Mode:** Execution — infra hardening (security group ingress)
**Model:** Opus 5

---

## Context

Session opened as an urgent security question: **NGINX2ROOT** was disclosed
today (2026-11-18) by Xint — five nginx CVEs plus a chained Linux kernel
SCTP bug that escalates an nginx-worker compromise to root on the host.
Lead flaw **CVE-2026-123007** is an integer overflow in HTTP/2 flow
control producing a heap out-of-bounds write; present since nginx 1.9.5
(2015), affecting every release through 1.31.8. Fixed in **1.30.7
(stable)** / **1.31.9 (mainline)**, both released 2026-11-18.

### NGINX2ROOT audit result: this site is NOT vulnerable to any of the five

The origin reports `server: nginx/1.30.4` — **inside** the affected range,
so the vulnerable code is on disk. What saves us is that none of the five
code paths are enabled. Audited against both Terraform-managed nginx
configs (`infra/phase3/templates/nginx-main.conf.tftpl` and
`nginx-site.conf.tftpl` — the whole config is managed, so this is a
complete audit, not just a vhost spot-check):

| CVE | Precondition | This site |
|---|---|---|
| CVE-2026-123007 | HTTP/2 enabled on listener (TLS/ALPN) | No `http2` directive anywhere; no TLS listener at all |
| CVE-2026-123633 | HTTP/2 + proxied upstream | No HTTP/2 |
| CVE-2026-121810 | HTTP/3/QUIC + proxied upstream | No QUIC listener |
| CVE-2026-113425 | Mail proxy with `proxy on` + `auth_http` | No `mail {}` block |
| CVE-2026-123634 | `resolver` + request-derived `proxy_pass` + `mirror` | None of the three |

CVE-2026-123634 is the only one reaching an HTTP/1.1-only reverse proxy,
so it got the closest look: it needs request-time DNS resolution of an
upstream. Ours is `upstream gunicorn { server unix:/run/gunicorn/gunicorn.sock; }`
with a literal `proxy_pass http://gunicorn;` — static unix socket, no
variables in `proxy_pass`, no `resolver`, no `mirror`.

**The HTTP/2 on the site is not nginx's HTTP/2.** `cloudfront.tf:53` sets
`http_version = "http2and3"` — that is CloudFront's viewer-side
implementation (AWS-managed code). `cloudfront.tf:80` sets
`origin_protocol_policy = "http-only"` and no cache behavior enables
gRPC, so CloudFront speaks HTTP/1.1 to the origin. The HTTP/2 in the
stack never touches nginx's vulnerable parser.

**Patch path:** Amazon Linux 2023's nginx package is **"Pending Fix"**
per the ALAS entry for CVE-2026-123007 — there is no fixed `dnf` package
to install yet. Patch rides the normal cadence once ALAS ships it; no
emergency patch tonight.

### Why this session exists anyway

The audit surfaced a real gap that the disclosure argues for closing:

1. **Port 80 is open to `0.0.0.0/0`** (`security_groups.tf:39-46`), so
   nginx is directly reachable from the internet rather than only via
   CloudFront. Carried as an open item since S20.
2. **The S20 `return 444` default_server catchall is not a mitigation for
   this class of bug.** Connection and protocol parsing happen *before*
   `server_name` selection, so a memory-corruption bug in the parser
   fires before nginx ever decides to return 444. S20 framed the 444
   catchall as closing "the behavioral gap without needing the SG
   change" — true for scanner noise and `DisallowedHost` log spam, but
   it buys nothing against a parser-level memory bug. The SG restriction
   is the control that would actually have helped, and is what makes the
   next nginx parser CVE a non-event.

### Scope explicitly out of this session
- **Patching nginx to 1.30.7** — no AL2023 package available yet
  (Pending Fix). Separate follow-up once ALAS publishes.
- **CloudFront WAF managed rules** — still rejected on cost/value
  grounds per S20.
- **HSTS ramp** — unrelated; still open, now unblocked (see follow-ups).

---

## Decisions locked this session

### Use the AWS-managed CloudFront prefix list directly — no Lambda, no scheduled refresh

| Area | Decision |
|---|---|
| Choice | Add `data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing"` resolving `com.amazonaws.global.cloudfront.origin-facing` by name, and point the port-80 ingress rule at `prefix_list_id` instead of `cidr_ipv4 = "0.0.0.0/0"`. |
| Why | **This corrects an incorrect assumption from S20.** S20 scoped this item as "nontrivial (AWS-managed prefix list `com.amazonaws.global.cloudfront.origin-facing` changes IPs continuously; needs a Lambda or scheduled TF refresh to keep the SG rule current)" and deferred it on that basis. That is wrong for the *managed* list: AWS creates and maintains it, and a security group rule referencing the prefix list ID picks up entry changes automatically at no cost. The Lambda/`ip-ranges.json`-parsing pattern is the legacy approach from before AWS published this list. Removing that phantom complexity is what makes this a short session rather than the "own session" S20 projected. **Why resolve by name via a data source rather than hardcoding `pl-…`.** The prefix list ID is region-specific, so hardcoding is both wrong-by-region and exactly the "never guess AWS resource identifiers" failure mode from CLAUDE.md. The data source resolves at plan time. |

### Delete the port-443 ingress rule rather than converting it

| Area | Decision |
|---|---|
| Choice | Remove `aws_vpc_security_group_ingress_rule.ec2_https` (443 from `0.0.0.0/0`) entirely instead of repointing it at the prefix list. |
| Why | **It is a dead rule.** Nothing listens on 443 on the box — `nginx-site.conf.tftpl` declares only `listen 80` / `listen [::]:80`, and CloudFront never dials 443 because `origin_protocol_policy = "http-only"`. The rule is pure attack surface with no function; its S12-era description ("Session 13+ once CloudFront fronts and terminates TLS") describes an architecture we did not end up building, since CloudFront terminates TLS and talks plaintext to the origin inside the VPC path. **It is also load-bearing for the quota.** The CloudFront managed prefix list has a **weight of 55** against the default "inbound rules per security group" quota of **60** — and AWS counts the list's published weight, not its current entry count. Referencing it on both 80 and 443 would consume 110 and the apply would fail. So deleting the dead 443 rule is what lets the port-80 lockdown fit without a quota-increase request. Post-change inbound count: **55 of 60**. |

### IPv4 prefix list only — IPv6 ingress stays closed

| Area | Decision |
|---|---|
| Choice | Reference only `com.amazonaws.global.cloudfront.origin-facing` (IPv4). Do **not** add the companion `com.amazonaws.global.ipv6.cloudfront.origin-facing`. |
| Why | The EC2 SG has **no IPv6 ingress rule today**, so IPv6 inbound is already denied by default-deny and nginx's `listen [::]:80` is unreachable from outside. Adding the IPv6 companion list would weigh another 55 (total 110) and blow the 60-rule quota to buy access that nothing currently needs. If IPv6 viewer traffic ever needs to reach the origin directly, that is a quota-increase conversation, not a default. Leaving the `listen [::]:80` line in nginx is harmless and avoids a config change with no behavioral effect. |

### Guardrail unit test lives in the Django suite

| Area | Decision |
|---|---|
| Choice | Add `InfraSecurityGroupTests` to `backend/config/tests.py` — parses `infra/phase3/security_groups.tf` and asserts the EC2 SG exposes no `0.0.0.0/0` ingress and that port 80 is gated on the CloudFront prefix-list data source. |
| Why | No test in this repo has ever read a `.tf` file, so this establishes a pattern — justified because the site lives unattended until June 2027 and the failure mode (someone, or a future session, "temporarily" restoring `0.0.0.0/0` to debug and leaving it) is silent and exactly the thing this session is closing. **Why the Django suite and not a separate runner.** `manage.py test` is the only test gate wired into CI — `.github/workflows/pr-checks.yml:65` and `deploy.yml:94` both run it — so a test placed anywhere else would not actually block a regression. Precedent: S20's `ProductionLoggingWiringTests` asserts on config wiring rather than code behavior in the same file. **Why text-parsing and not a live AWS assertion.** Tests must pass in CI with no AWS credentials and in `terraform destroy`-ed states; asserting on the declared intent in HCL is the part that belongs in a unit test. Live-state verification is the post-apply smoke step instead. |

---

## Progress

- [x] Session log created (this file).
- [x] NGINX2ROOT exposure audit — not vulnerable to any of the five (see Context).
- [x] `infra/phase3/security_groups.tf` — prefix-list data source added; port 80 repointed at it; dead 443 rule removed; file-header comment updated.
- [x] `terraform fmt -check -diff` clean (exit 0) and `terraform validate` → "Success! The configuration is valid."
- [x] Unit tests — `InfraSecurityGroupTests` (7 cases) in `backend/config/tests.py`. **82/82 passing** (75 pre-existing + 7 new).
- [x] Negative-control check on the tests — see [Test negative control](#test-negative-control) below.
- [x] Confirmed `.claude/launch-checklist.md` needs no edit: it contains no direct-to-origin probes (grep for `ec2_public_dns` / `EC2_HOST` / `compute-1` → no hits). The commands this change invalidates live only in the S18/S20 session logs, which are historical records and are left as-written; the replacement method is recorded under follow-ups instead.
- [x] `terraform plan` reviewed — **the full-workspace plan is unsafe to apply**; see [Digression: pending AMI drift](#digression-pending-ami-drift-wants-to-rebuild-the-instance). Prefix list resolved correctly to `pl-3b927c52` (us-east-1 CloudFront origin-facing).
- [ ] **Targeted** apply of the SG rules only (command in the digression below).
- [ ] Post-apply smoke (see [Verification plan](#verification-plan)).

---

## Digression: pending AMI drift wants to rebuild the instance

The first `terraform plan` of this session came back **3 to add, 1 to
change, 4 to destroy** — not the 1/0/2 this session's change accounts
for. The extra churn is **pre-existing drift, unrelated to the SG work**,
and it includes `aws_instance.web must be replaced`.

**Cause.** `ec2.tf:30` resolves the AMI from the AWS-published SSM
parameter `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64`.
Amazon updates that parameter on every new AL2023 AMI publication, and
`ami` is a ForceNew attribute on `aws_instance`. The last apply was
~2026-08-23, so the parameter has moved and **every apply from now on
wants to rebuild the box** until this is dealt with.

**Not the cause:** the large `user_data_base64` diff in the plan.
`user_data_replace_on_change = false` (ec2.tf:62) is set deliberately
(rationale at ec2.tf:25-28), so the drifted bootstrap script does not
force replacement on its own. It drifted because S20's nginx template is
embedded in `user_data` and S20 shipped that change via `deploy.sh` /
`wedding-nginx-sync.sh` rather than by rebuilding. The follow-on
`aws_eip_association.web` replacement and `aws_iam_role_policy.github_deploy`
update are both just consequences of the instance id/ARN changing.

**Resolution for this session: targeted apply.** `-target` is normally a
smell, but this is its legitimate use — shipping a narrow intended change
while unrelated drift sits pending:

```bash
terraform -chdir=infra/phase3 apply \
  -target=aws_vpc_security_group_ingress_rule.ec2_http \
  -target=aws_vpc_security_group_ingress_rule.ec2_https
```

Expect `1 to add, 0 to change, 2 to destroy` and no mention of
`aws_instance.web`.

**Why not just take the rebuild now.** Blast radius is genuinely bounded
— Postgres is on RDS, media is on S3, and ec2.tf:9-12 deliberately keeps
the EIP outside the instance lifecycle so a replacement retains
`32.199.50.156` and CloudFront's origin does not move. A previous session
clearly anticipated AMI-bump replacement. Even so, deferred because:

1. **It buys nothing for NGINX2ROOT.** AL2023's nginx is still Pending
   Fix, so a fresh AMI today ships the same vulnerable 1.30.4.
2. **`user_data` has not been boot-tested in its current form.** It has
   drifted since S20, and the last end-to-end exercise of the bootstrap
   was S16 — a session that exists *because* bootstrap broke.
3. Downtime is a full cloud-init cycle (dnf, pip, clone, migrate,
   collectstatic), with CloudFront erroring on uncached paths — not
   something to absorb incidentally during an urgent security session.

The right vehicle is a deliberate rebuild session once AL2023 publishes
the nginx fix: that bundles the OS patches, the nginx patch, and a real
boot-test of `user_data` under an agenda where all three are the point.

---

## Test negative control

A guardrail test that only ever runs against the fixed config proves
nothing, so the suite was re-run against the **pre-lockdown** config
(`git show HEAD:infra/phase3/security_groups.tf`, which has 4
occurrences of `0.0.0.0/0`) with `_SECURITY_GROUPS_TF` monkeypatched to
point at it. Result: **4 of 7 failed**, which is the correct outcome.

| Test | vs. old config | Correct? |
|---|---|---|
| `test_no_ingress_rule_is_open_to_the_world` | FAIL — `ec2_http, ec2_https` | ✓ bites |
| `test_http_ingress_is_gated_on_the_cloudfront_prefix_list` | FAIL | ✓ bites |
| `test_prefix_list_is_resolved_by_name_not_a_hardcoded_id` | FAIL — data source missing | ✓ bites |
| `test_dead_port_443_ingress_rule_stays_deleted` | FAIL | ✓ bites |
| `test_parser_found_the_expected_rule_resources` | pass | ✓ anchor — those resources exist in both |
| `test_ipv6_ingress_stays_closed` | pass | ✓ old config had no IPv6 ingress either |
| `test_egress_still_allows_outbound` | pass | ✓ egress untouched by this session |

The three that still pass are the ones that *should* pass in both
states — the vacuity anchor plus two invariants this session did not
change. The temp file was removed afterwards; nothing in the repo was
modified to run this.

---

## Verification plan

Post-apply. The direct-to-EC2 probes from the S20 smoke suite should now
**time out** rather than return 444 — that inversion is the whole point,
and is the clearest single signal the lockdown took effect.

```bash
# 1) Public path through CloudFront — must still be 200.
curl -sI "https://kaitlynandsteventietheknot.com/" | grep -E '^HTTP|^x-cache'

# 2) Direct-to-origin — must now TIME OUT (connection never established).
#    Pre-change this returned 444/empty-reply; post-change the SYN is dropped.
EC2_HOST=$(terraform -chdir=infra/phase3 output -raw ec2_public_dns)
curl -v --max-time 5 "http://${EC2_HOST}/" || echo "expected: timeout / no route"

# 3) Confirm the SG rule resolved to the prefix list, not a CIDR.
SG_ID=$(terraform -chdir=infra/phase3 output -raw ec2_security_group_id)
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=$SG_ID" \
  --query 'SecurityGroupRules[?!IsEgress].{Port:FromPort,Cidr:CidrIpv4,PrefixList:PrefixListId}' \
  --output table

# 4) All pages still serving (CloudFront may serve cached; add a cache-buster).
for p in / /travel/ /registry/ /rsvp/ /gallery/; do
  printf "%-12s " "$p"
  curl -so /dev/null -w "%{http_code}\n" "https://kaitlynandsteventietheknot.com$p?cb=$RANDOM"
done
```

Also confirm the deploy path still works end-to-end, since it is the
thing most likely to be quietly broken by an ingress change: SSM is
outbound-only from the instance so it should be unaffected, and
`deploy.sh`'s post-flight check curls `http://localhost/` on the box
rather than coming in through the SG. Next merge to main is the real test.

---

## Open questions / follow-ups

*(Carrying S20 handoff plus new items.)*

- **NEW — deliberate instance-rebuild session.** Pairs with the nginx
  patch below. Agenda: boot-test the drifted `user_data`, take the ~3
  months of accumulated AL2023 OS patches, confirm the EIP survives the
  replacement as ec2.tf:9-12 intends, and verify the rebuilt box comes
  up with the Session 21 SG in place. Until this happens, **every
  `terraform apply` in phase3 must be `-target`ed**, or it will rebuild
  the instance as a side effect. See the digression above.
- **NEW — decide whether to keep tracking the `-latest` AMI parameter.**
  Tracking it means never silently running a stale AMI, at the cost of
  never having a clean `plan` and of every apply carrying an implicit
  instance rebuild. The alternative is pinning the AMI id in a variable
  and bumping it intentionally (which fits this repo's strict-version-pin
  convention better). Not urgent, but the current setup is a foot-gun
  that this session tripped over, and it will trip the next one too.
- **NEW — patch nginx to 1.30.7 when AL2023 ships it.** Currently
  "Pending Fix" in ALAS for CVE-2026-123007. Not reachable in our
  config (see Context), so this is hygiene rather than urgency, but the
  vulnerable code is installed and should not stay installed. Check
  `dnf check-update nginx` on the box, or watch the ALAS entry.
- **NEW — direct-to-origin debugging is gone by design.** The S18 and S20
  smoke suites curl the EC2 public DNS directly; those commands now time
  out. `.claude/launch-checklist.md` was checked and contains no such
  probe, so nothing in the live operational doc breaks. The replacement
  for "is the origin healthy independent of CloudFront" is an SSM
  `send-command` running `curl -H "Host: $DOMAIN" http://localhost/` on
  the box. If a future session wants an origin-health line in the launch
  checklist, that is the form it should take — deliberately not added
  here, since the checklist has never had one and inventing a new
  checklist item was outside this session's scope.
- **NEW — SG inbound rule budget is now 55/60.** Any future inbound rule
  on the EC2 SG has 5 slots. If something needs more (or IPv6 origin
  access), request a quota increase on "Inbound or outbound rules per
  security group" (L-0EA8095F) rather than reverting to CIDR rules.
- **HSTS ramp** — S19/S20 gated this on the ERROR/CRITICAL filter staying
  quiet. It has been quiet since 2026-08-23 (≈3 months), so the gate is
  satisfied and this is unblocked. Next session candidate.
- **CloudWatch `filter-log-events` JSON pattern not matching** — carried
  from S20; deliverable is a `scripts/cloudwatch-*.sh` helper.
- **Watch for scanner waves patterning past the nginx regex list** —
  carried from S20.
- **CloudFront WAF managed rules** — still rejected on cost/value.
- **RDS deletion protection** — flip 2027-01/02.
- **Auto-invalidation on Photo save** — deferred from S19.
- **Photo alt-text / captions** — admin follow-up.
- **`<picture>` mobile crop for hero** — carried from S15.
- **`django-vite`** — deferred, not blocking.
- **Remove/narrow cloud-init's `(ALL) NOPASSWD: ALL` grant to ec2-user**
  — carried from S19.
