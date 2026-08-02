# Session 11 — Phase 3 middle: VPC + subnets + security groups + RDS Postgres

**Date:** 2026-08-02 (rolled directly from Session 10)
**Mode:** Execution — Phase 3 middle (partial AWS provisioning; RDS starts billing)
**Model:** Opus 4.7

---

## Context

Session 10 (`2026-08-02-session-10-phase3-s3-storages-and-logging.md`)
landed the S3 media + static buckets, the IAM policy document for the
future EC2 instance role, `django-storages` wiring in production settings,
and structured JSON logging with surgical logger calls in the RSVP submit
path and Photo save signal. Test count went from 31 to 44. Terraform state
under `infra/phase3/` has 8 resources.

Session 11 extends the same `infra/phase3/` module with the network + DB
layer. When this session lands, the module will additionally have:

- A dedicated VPC (10.0.0.0/16), one public subnet (10.0.1.0/24) and one
  private subnet (10.0.11.0/24) in the same AZ per the handoff (no NAT
  gateway = no $32/mo NAT charge).
- Internet Gateway + a public route table with a default route to it.
  Private route table has no default route — the private subnet is only
  reachable from resources inside the VPC.
- Two security groups: one for the future EC2 instance (empty this session
  — Session 12 attaches 80/443/22 ingress rules), one for RDS accepting
  only 5432 from the EC2 SG (reference-by-SG, not CIDR).
- RDS db.t3.micro running Postgres 17.10, 20 GB gp3, backup retention 7
  days, PostgreSQL log export to CloudWatch, deletion_protection false,
  skip_final_snapshot true.

**Cost note (user confirmed before apply this session):** RDS db.t3.micro
on-demand is ~$13/mo. gp3 storage 20 GB is ~$2/mo. CloudWatch log
ingestion + storage is fractions of a cent at this traffic. Full stack
after Session 11 apply: ~$15/mo, up from the ~$0.60/mo of Session 10.

**Why no NAT gateway:** the private subnet holds only RDS, which never
needs outbound internet (patches come via AWS's internal maintenance
window). NAT gateways are ~$32/mo + per-GB — not worth it for a DB that
doesn't call out.

**Why single AZ:** wedding site with a ~10-month lifespan; Multi-AZ
doubles the RDS bill (~$26/mo instead of $13). AZ failures are rare
(measured in a few per year across all AZs) and RDS automated snapshots
give point-in-time restore into a different AZ if the primary AZ dies.
User confirmed single-AZ is fine.

**No app-code changes this session.** RDS is provisioned but nothing
connects to it — EC2 doesn't exist yet, and local dev keeps using SQLite
via `local.py`. `production.py` is already wired for RDS via env vars
from Session 10 (Django read `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_HOST`, `DB_PORT`). Session 12 will point those at the RDS endpoint
this session outputs.

Out of scope this session (deferred):

- **EC2** — Session 12.
- **EC2 SG ingress rules** — Session 12 attaches 80/443/22 to the
  placeholder SG declared here.
- **CloudFront distribution + DNS cutover + phase 0 destroy** —
  Session 12 or 13.
- **CloudWatch Agent, log groups, retention, ERROR alarm** — Session 12+
  (needs EC2 to run the agent).
- **GitHub Actions OIDC deploy role** — Session 12+.
- **Testing the DB connection from Django** — nothing to test against
  yet; Session 12's first task will be a `manage.py migrate` from EC2
  once the DB is reachable.
- **Bastion / SSM tunnel for direct DB access from laptop** — RDS is in
  a private subnet, unreachable from anywhere except (future) EC2. If we
  need direct psql access for admin queries, Session 12+ can add an
  `aws ssm start-session --target <ec2> --document-name AWS-StartPortForwardingSessionToRemoteHost`
  runbook.

## Session plan

1. Create this session log (in progress).
2. **`vpc.tf`** — `aws_vpc` at 10.0.0.0/16, one public subnet
   (10.0.1.0/24) + one private subnet (10.0.11.0/24) in the same AZ
   (`us-east-1a`), `aws_internet_gateway`, public route table with default
   route to IGW, private route table with only the local route (implicit).
   Enable DNS hostnames on the VPC so RDS gets a resolvable endpoint.
3. **`security_groups.tf`** —
   - `aws_security_group.ec2` — placeholder for the EC2 instance's SG.
     No inline ingress rules; Session 12 attaches 80/443/22 via
     `aws_vpc_security_group_ingress_rule` resources. Egress open (SG
     defaults allow-all egress in Terraform, but AWS strips that on
     creation — so declare an explicit `aws_vpc_security_group_egress_rule`
     to `0.0.0.0/0`).
   - `aws_security_group.rds` — accepts 5432 inbound *only* from the EC2
     SG (reference-by-SG). No egress needed (RDS doesn't initiate
     outbound; but we'll add an all-egress rule for consistency and for
     RDS internal maintenance traffic).
4. **`rds.tf`** —
   - `aws_db_subnet_group.private` grouping the private subnet (plus a
     second private subnet? RDS requires ≥2 subnets in different AZs for
     the subnet group even for single-AZ instances). This is a wrinkle —
     see "Decisions locked" below.
   - `aws_db_instance.wedding` — Postgres 17.10, `db.t3.micro`, 20 GB gp3,
     encrypted at rest (aws/rds KMS), backup_retention_period 7,
     backup_window "07:00-09:00" UTC (early morning US), maintenance
     window "sun:09:00-sun:11:00" UTC, deletion_protection false,
     skip_final_snapshot true, apply_immediately false,
     enabled_cloudwatch_logs_exports ["postgresql"],
     performance_insights_enabled false (extra cost, not worth it here).
5. **`variables.tf`** — add:
   - `db_master_username` (default `wedding_admin` — not `postgres`, small
     OpSec win).
   - `db_master_password` (sensitive, no default, must be provided in
     `terraform.tfvars`).
   - `db_name` (default `wedding`).
6. **`terraform.tfvars.example`** — add commented lines for the three
   new vars, with a callout that `db_master_password` MUST be set in
   the gitignored `terraform.tfvars`.
7. **`outputs.tf`** — add:
   - `db_endpoint` (host:port, from `aws_db_instance.wedding.endpoint`).
   - `db_address` (host only).
   - `db_port`.
   - `db_name` (the DB name from the var).
   - `vpc_id`, `public_subnet_id`, `private_subnet_ids` (list, for
     Session 12's EC2 module).
   - `ec2_security_group_id` (Session 12 attaches ingress rules to it).
8. **`README.md`** — extend with Session 11 additions: RDS cost line,
   updated first-apply resource count, "Setting `db_master_password`"
   subsection, DB verification snippet (via SSM tunnel — deferred but
   documented).
9. `terraform init` (re-init to pick up any new provider features) +
   `terraform validate` + `terraform fmt -diff`.
10. Hand `terraform plan -out=tfplan` + `apply` to the user
    ([[feedback-long-running-commands]]). RDS provisioning is
    ~5-10 minutes, longer than Session 10.
11. Finalize this log (no test changes — no app code touched).

---

## Decisions locked this session

### `aws_db_subnet_group` needs two AZs even for single-AZ instances

| Area | Decision |
|---|---|
| Problem | RDS subnet groups require subnets in **at least two Availability Zones**. Even a single-AZ `db.t3.micro` instance can't be created in a subnet group that spans only one AZ. This bites on the "one AZ, no NAT" simplification. |
| Fix | Create a **second private subnet** in a second AZ (10.0.12.0/24 in `us-east-1b`) purely to satisfy the subnet group. RDS still runs single-AZ in the primary; the secondary subnet is empty and free (VPC subnets are free). |
| Impact | Cost: zero. Complexity: one extra `aws_subnet` resource + one extra route-table association. The private route table still has only the local route, no default route out. |
| Note | If we later want Multi-AZ (or if a snapshot restore needs to land in the secondary AZ), the second subnet is already there — no re-plumbing needed. |

### VPC CIDR + subnet layout

| Area | Decision |
|---|---|
| VPC CIDR | 10.0.0.0/16 — 65k addresses, standard AWS example range. |
| Public subnet | 10.0.1.0/24 in `us-east-1a` — 251 usable IPs, plenty for one EC2. |
| Private subnet A | 10.0.11.0/24 in `us-east-1a` — RDS lives here. |
| Private subnet B | 10.0.12.0/24 in `us-east-1b` — subnet-group filler; empty. |
| Reserved | 10.0.2.0/24 (public B) and 10.0.13.0/24 (private A2) unreserved but usable if we ever add a second public subnet. |

### Postgres 17.10 + `db.t3.micro` + 20 GB gp3

| Area | Decision |
|---|---|
| Engine version | Postgres 17.10 (latest RDS-supported minor of 17.x, confirmed via `aws rds describe-db-engine-versions --engine postgres`). Exact-pinned per [[feedback-strict-version-pins]]. |
| Instance class | `db.t3.micro` per handoff. 2 vCPU burst + 1 GB RAM; adequate for wedding-site RSVP writes. |
| Storage | 20 GB gp3 (baseline 3000 IOPS + 125 MB/s throughput free). No autoscaling this session — 20 GB is more than enough for guest data. |
| Encryption at rest | Enabled with AWS-managed `aws/rds` KMS key. Free. |
| Backup retention | 7 days. Cheap; enables point-in-time restore. |
| Deletion protection | **false** for now. Post-wedding teardown needs to be a single `terraform destroy`. If we get worried closer to the wedding date, flip to true and require a two-step destroy. |
| Final snapshot | `skip_final_snapshot = true`. Same reasoning — post-wedding cleanup should be one command. Session 15+ can revisit if we want a keepsake export. |

### Master credentials in tfvars, not env vars

| Area | Decision |
|---|---|
| Where | `db_master_password` lives in `infra/phase3/terraform.tfvars` (gitignored) as a sensitive Terraform variable. |
| Why not AWS Secrets Manager | Overkill for a single wedding-site DB. Secrets Manager costs $0.40/mo per secret + API calls; tfvars is free. Post-wedding, `terraform destroy` cleanly removes the password from state (state itself is local). |
| Rotation | None planned. Wedding-site lifespan is ~10 months; single-tenant DB with one app connecting. Manual rotation is trivial if ever needed. |
| Master username | `wedding_admin` rather than `postgres`. Very small OpSec win — makes generic "postgres/postgres" scanners fail before hitting a real credential check. Not a security control, just noise reduction. |

### CloudWatch log export scope

| Area | Decision |
|---|---|
| Enabled logs | `postgresql` only (from the RDS list of `postgresql`, `upgrade`). Skips `upgrade` because we don't do in-place engine upgrades on this DB. |
| Log group name | AWS-assigned: `/aws/rds/instance/${db_id}/postgresql`. Per handoff amendment, we do not override — RDS writes there directly and Terraform declaring our own log group would conflict. |
| Retention | RDS creates the log group with **default retention (never expire)** unless we explicitly `aws_cloudwatch_log_group` it. Per the critical rules, we must set retention. **Declare an `aws_cloudwatch_log_group` with `retention_in_days = 30` matching the handoff amendment**, and add a `depends_on` so the log group exists before the DB starts writing. |

### No RDS Proxy, no read replica

| Area | Decision |
|---|---|
| RDS Proxy | Skipped. $0.015/hr per vCPU (~$11/mo for two vCPU) with no meaningful benefit for a single-app single-instance DB. |
| Read replica | Skipped. Wedding-site traffic is low; the primary handles both reads and writes fine. |

### Out-of-scope defer log

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **CloudFront distribution / DNS cutover / phase 0 destroy** — Session 12 or 13.
- **EC2 + gunicorn + nginx + IAM role attachment** — Session 12.
- **GitHub Actions OIDC deploy role** — Session 12+.
- **CloudWatch Agent + custom log groups + ERROR alarm** — Session 12+.
- **RDS Proxy, read replicas, Multi-AZ** — probably never for this project.
- **Deletion protection flip pre-wedding** — track as an Open Question.

---

## Progress

- [x] Session log created (this file).
- [ ] `vpc.tf` written (VPC + 3 subnets + IGW + route tables + associations).
- [ ] `security_groups.tf` written (EC2 placeholder + RDS accepting from EC2 SG).
- [ ] `rds.tf` written (subnet group + DB instance + CloudWatch log group).
- [ ] `variables.tf` extended with `db_master_username`, `db_master_password`, `db_name`.
- [ ] `terraform.tfvars.example` extended with commented DB var placeholders.
- [ ] `outputs.tf` extended with DB endpoint + VPC/subnet + SG outputs.
- [ ] `README.md` extended with Session 11 additions.
- [ ] `terraform init` + `validate` + `fmt -diff` clean.
- [ ] User runs `terraform plan -out=tfplan` + `apply` (5-10 min).
- [ ] Session log finalized.

### Digressions worth remembering

*(Filled in during execution.)*

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-02-session-11-phase3-vpc-and-rds.md` — this log
- `infra/phase3/vpc.tf`
- `infra/phase3/security_groups.tf`
- `infra/phase3/rds.tf`

**Modified:**
- `infra/phase3/variables.tf` — add DB vars
- `infra/phase3/terraform.tfvars.example` — add commented DB placeholders
- `infra/phase3/outputs.tf` — add DB + VPC/subnet + SG outputs
- `infra/phase3/README.md` — Session 11 additions

**Not touched:** any file under `backend/` — no app-code changes this session.

Per working contract, all `git add` / `git commit` is left to the user.

## Session 12 handoff

Session 12 is the EC2 lift + CloudFront distribution + DNS cutover + phase 0
destroy. This is a big session; may split into 12a / 12b if it grows.

1. **EC2** — `aws_instance` on `t3.micro` in the public subnet
   (Session 11 output), Amazon Linux 2023 AMI (latest via SSM parameter),
   IAM instance profile with the Session 10 S3 policy JSON attached +
   `AmazonSSMManagedInstanceCore`. Elastic IP attached. Attach to the
   Session 11 `ec2_security_group_id`.
2. **EC2 SG ingress rules** — 80/443 from `0.0.0.0/0`, 22 from user's
   home IP `/32` (user provides). Added via
   `aws_vpc_security_group_ingress_rule` resources targeting the SG
   from Session 11.
3. **CloudFront distribution** — the real one, with two origins: S3
   media bucket for `/media/*`, EC2 elastic IP for everything else.
   AllowCloudFrontOACRead bucket policies uncommented in
   Session 10's `s3_media.tf` / `s3_static.tf` (or added fresh in a new
   `cloudfront.tf`). Scoped to this new distribution's ARN.
4. **Static also via CloudFront** — a second cache behavior on the static
   bucket for `/static/*`. Path-based routing.
5. **Route 53 cutover** — apex + www alias records swap from phase 0
   distribution to the new one. Because they're aliases, TTL is
   instantaneous.
6. **Phase 0 destroy** — after the new distribution is healthy and DNS
   has cutover, `cd infra/phase0 && terraform destroy`. Update `phase0/README.md`
   to note retirement.
7. **First deploy** — EC2 first-boot script (user_data) that installs
   gunicorn + nginx + Python deps, git-clones the repo, runs
   `manage.py migrate` (first hit to RDS!), `collectstatic` (first hit
   to S3 static), and starts gunicorn via systemd.
8. **CloudWatch Agent** — install via user_data, config file shipped
   from the repo (`infra/phase3/cloudwatch-agent-config.json` — new
   file). Tails journald + nginx logs. Log groups (`/wedding/django`,
   `/wedding/gunicorn`, `/wedding/nginx/access`, `/wedding/nginx/error`,
   `/wedding/system`) created in Terraform with `retention_in_days = 30`.
9. **Instance role S3 policy attachment** — the Session 10
   `ec2_s3_policy_json` output gets attached via `aws_iam_role_policy`
   this session.
10. **GitHub Actions OIDC deploy role** — trust policy scoped to the
    specific repo; policy attached: SSM `send-command` + read on the
    instance ID + a small S3 read for artifacts. `.github/workflows/deploy.yml`
    from the handoff, minus the `apt/ubuntu` paths (this is AL2023).

**Cost after Session 12 apply:** EC2 t3.micro (~$7.50/mo on-demand, or
~$5/mo with 1yr Savings Plan), elastic IP (free while attached), CloudFront
(free tier covers wedding-site traffic), CloudWatch logs (fractions).
Total site cost: ~$25/mo.

Before touching anything in Session 12:

- Read this file (Session 11), plus Session 10's storages + logging notes.
- **Python:** `/Users/stevennielsen/aws-wedding-website/.venv/bin/python`.
- **Frontend:** `pnpm` via corepack from `frontend/`.
- **Runserver:** 8765. **Vite dev:** `http://localhost:5175/`, not `127.0.0.1`.
- Every direct Terraform provider / module version gets exact-pinned per [[feedback-strict-version-pins]].
- Long-running `terraform apply` / `destroy` handed to the user per [[feedback-long-running-commands]].
- **`awscrt`** already in the venv from Session 10, still needed for any Python-side AWS work per [[user-aws-sso-auth]].

## Open questions / follow-ups

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Photo alt-text values** — final copy still pending.
- **Deletion protection on RDS** — flip to true closer to the wedding? Track
  as a pre-wedding hardening task.
- **User's home IP `/32`** for the SSH ingress rule in Session 12 — the
  user needs to provide this at apply time, or we use an SSM-only setup
  and skip SSH entirely (probably cleaner — SSM session manager is more
  auditable than SSH).
- **`<picture>` mobile crop** for hero — Session 12+.
- **`django-vite`** — still deferred.
- **Real gallery page** — Session 13+.
- **Handoff `apt`/`ubuntu` cleanup** — Session 12 (drops the last of it).
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3 tail.
