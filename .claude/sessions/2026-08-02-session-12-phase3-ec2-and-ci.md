# Session 12 — Phase 3 tail: EC2 + first deploy + CI workflow

**Date:** 2026-08-02 (third session same day)
**Mode:** Execution — Phase 3 tail (compute + first deploy; no public URL change)
**Model:** Opus 4.7

---

## Context

Session 11 (`2026-08-02-session-11-phase3-vpc-and-rds.md`) landed the VPC
+ subnets + security groups + RDS Postgres. The DB endpoint is
`wedding-site-postgres.cc70gwu6slkq.us-east-1.rds.amazonaws.com:5432`,
`available`, private-subnet only, waiting for a client. Session 12
adds that client: an EC2 t3.micro running gunicorn + nginx, serving
the Django app on port 80 at an Elastic IP.

**Original handoff had 10 sub-tasks for "Session 12" — split into 12 / 13 /
14 for reviewability.** The user confirmed the split at the start of this
session:

- **Session 12 (this one):** EC2 + IAM role + SSM Parameter Store for
  secrets + user_data first-boot script (installs deps, clones repo,
  builds frontend, migrates DB, starts gunicorn + nginx) + CI workflow
  (ruff + tests on push/PR to any branch). Public URL stays on phase 0.
  End state: `http://<eip>/` serves the site.
- **Session 13:** CloudFront distribution (3 behaviors — media/static/EC2),
  OAC bucket policies, Route 53 apex+www cutover, phase 0 destroy,
  branch protection on `main`.
- **Session 14:** CloudWatch Agent + log groups + retention + ERROR
  alarm, GitHub Actions OIDC role + `.github/workflows/deploy.yml`.

**Why site-on-EIP-first, not straight to CloudFront:** debugging the app
tier is significantly easier when only one thing changed. If the site
works on the EIP but breaks behind CloudFront, we know the delta is
CloudFront. Also — Session 13's DNS cutover is irreversible in
under-DNS-TTL time; we want that to be a "flip a healthy stack" moment,
not a "cut over and hope."

**Secrets strategy — confirmed with user:** SSM Parameter Store
SecureString for secrets, plain String for non-secrets, all under
`/wedding-site/prod/` prefix. Fetched at each deploy by user_data
(first-boot) and by the future GHA deploy workflow (Session 14). SSM
beats Secrets Manager at this scale — free, same IAM/KMS story, one
migration line to swap if we ever outgrow it.

**CI vs deploy split:** two workflows, distinct triggers. `ci.yml` runs
lint + tests on `push` (any branch) and `pull_request`. `deploy.yml`
(Session 14) runs only on `push` to `main` after OIDC role exists.
Landing CI without deploy this session avoids shipping a broken workflow.

**Branching strategy confirmation:** user has been direct-pushing to
`main` throughout; that stays the norm until Session 13 flips DNS. At
that point `main = production`, branch protection turns on, PR flow
becomes the rule. Between Session 12 and 13, direct pushes still land on
private EIP — safe.

Out of scope this session (deferred):

- **CloudFront distribution / bucket policies / DNS cutover / phase 0
  destroy** — Session 13.
- **HTTPS on EC2** — nginx serves HTTP-only this session; CloudFront
  terminates TLS in Session 13. No Let's Encrypt on EC2 (would just get
  ripped out).
- **CloudWatch Agent + log groups + ERROR alarm** — Session 14.
- **GitHub Actions OIDC deploy role + deploy.yml** — Session 14.
- **Branch protection on `main`** — Session 13.
- **`SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`,
  `CSRF_TRUSTED_ORIGINS`** — need CloudFront to make sense; add in
  Session 13 as part of the cutover PR.
- **Log rotation for gunicorn stderr** — Session 14's CloudWatch Agent
  makes it moot (journald ships everything, log group retention
  handles rotation). For this session, systemd's journald default
  behavior is fine.

## Session plan

1. Create this session log (in progress).
2. **`ssm.tf`** — `random_password.django_secret_key` (length 50,
   special chars only from a URL-safe set) + `aws_ssm_parameter`
   resources for every env var Django needs. SecureString for
   DJANGO_SECRET_KEY + DB_PASSWORD, String for the rest. All under
   `/wedding-site/prod/`.
3. **`ec2_iam.tf`** — trust policy for `ec2.amazonaws.com`; inline
   policies attaching the Session 10 `ec2_s3_policy_json` and a new
   `ssm:GetParametersByPath` scoped to `/wedding-site/prod/*`; managed
   policy attachment `AmazonSSMManagedInstanceCore`; instance profile.
4. **`security_groups.tf` extension** — 3 new
   `aws_vpc_security_group_ingress_rule` resources on the EC2 SG: tcp/80
   from `0.0.0.0/0`, tcp/443 from `0.0.0.0/0`, tcp/443 IPv6 from `::/0`.
   No port 22 — SSM Session Manager only.
5. **`ec2.tf`** —
   - `data.aws_ssm_parameter.al2023_ami` for the latest Amazon Linux
     2023 x86_64 AMI (AWS-published SSM parameter, always current).
   - `aws_instance.web` t3.micro, subnet_id = public subnet, IAM
     instance profile from step 3, associated to EC2 SG, user_data =
     `templatefile("templates/user_data.sh.tftpl", { ... })`.
   - `aws_eip.web` + `aws_eip_association.web` — permanent public IP so
     Session 13's CloudFront origin doesn't shift on instance replace.
6. **`templates/user_data.sh.tftpl`** — Bash script, runs once at first
   boot, idempotent-friendly:
   - `dnf update -y && dnf install -y python3.12 python3.12-devel nginx git nodejs20 postgresql17`
   - Enable corepack (bundled with Node 20), activate `pnpm@11.17.0`.
   - Clone the repo to `/home/ec2-user/aws-wedding-website`.
   - Create `.venv` with Python 3.12, install
     `backend/requirements/production.txt`.
   - `pnpm install --frozen-lockfile && pnpm build` in `frontend/`.
   - Fetch all `/wedding-site/prod/*` params via
     `aws ssm get-parameters-by-path --with-decryption --recursive` and
     render `backend/.env`.
   - `manage.py migrate --settings=config.settings.production`.
   - `manage.py collectstatic --settings=config.settings.production --noinput`.
   - Write `/etc/systemd/system/gunicorn.service` from a template baked
     into user_data (templatefile-inlined).
   - Write `/etc/nginx/conf.d/wedding-site.conf`.
   - `systemctl enable --now gunicorn nginx`.
   - Log the whole run to `/var/log/user-data.log` for post-mortem.
7. **`templates/gunicorn.service.tftpl`** — systemd unit:
   - `EnvironmentFile=/home/ec2-user/aws-wedding-website/backend/.env`
   - `User=ec2-user`, `Group=ec2-user`
   - `WorkingDirectory=/home/ec2-user/aws-wedding-website/backend`
   - `ExecStart=/home/ec2-user/aws-wedding-website/.venv/bin/gunicorn
     --workers 3 --bind unix:/run/gunicorn/gunicorn.sock config.wsgi:application`
   - `RuntimeDirectory=gunicorn` (systemd creates `/run/gunicorn` at
     start, cleans on stop).
   - `Restart=on-failure`, `RestartSec=5`.
8. **`templates/nginx-site.conf.tftpl`** — port 80 server block:
   - `server_name _;` (accept any Host — behind EIP, no DNS yet).
   - `location /static/` — proxy_pass would be wrong here since we're
     using S3 static. Actually since S3 static + Manifest is in use,
     `{% static %}` URLs resolve directly to the S3 bucket regional URL
     (until Session 13 wires CloudFront + AWS_STATIC_CUSTOM_DOMAIN).
     nginx doesn't serve `/static/` at all this session — clients hit
     S3 directly.
   - `location /media/` — same story: `MediaField.url` resolves to S3.
   - `location /` — proxy_pass to gunicorn's unix socket, standard
     `X-Forwarded-*` headers.
9. **`outputs.tf`** — add `ec2_instance_id`, `ec2_public_ip`,
   `ec2_public_dns`, `ec2_iam_role_arn`, `ssm_parameter_prefix`.
10. **`production.py`** — parse `ALLOWED_HOSTS` as comma-separated env
    var (fallback to `[DOMAIN]` if unset). One-line change; enables the
    EIP + real domain to coexist in the allow list.
11. **`pyproject.toml`** at repo root — `[tool.ruff]` config
    (line-length 100, target-version py312, select E/F/W/I/UP/B/SIM,
    per-file ignores for migrations + tests). Pin `ruff==<version>` in
    `backend/requirements/local.txt`.
12. **`.github/workflows/ci.yml`** — two parallel jobs:
    - `python` — checkout, setup-python 3.12, cache pip, install
      `backend/requirements/production.txt` + `local.txt`,
      `ruff check backend/`, `ruff format --check backend/`,
      `cd backend && python manage.py test`.
    - `frontend` — checkout, setup-node 20, corepack enable pnpm,
      `cd frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm build`.
    - Triggers: `push` (any branch) + `pull_request`.
    - No AWS creds, no deploy step.
13. **Grep + `terraform validate` + `terraform fmt -diff`** per the
    ASCII-only-descriptions memory.
14. **Local ruff** — run `ruff check` + `ruff format --check` against
    `backend/`. Fix any real issues (expect a few unused-import /
    line-length flags in the older code). Also run the full test suite
    once with the new ALLOWED_HOSTS test to confirm 45 tests pass.
15. Hand `terraform plan` + `apply` to user
    ([[feedback-long-running-commands]]). EC2 provision ~1 min; user_data
    (first boot with all deps + git clone + pnpm build + migrate +
    collectstatic) probably ~5-8 min.
16. Once EIP is live, `curl` verify the site responds.
17. Finalize this log.

---

## Decisions locked this session

*(Filled in during execution.)*

### AL2023 AMI via SSM parameter, not hardcoded

| Area | Decision |
|---|---|
| Choice | `data.aws_ssm_parameter { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64" }`. |
| Why | AWS publishes the current AMI ID under a stable SSM path per region. Hardcoding an `ami-xxx` value means the AMI drifts out of security-patch coverage over time. The SSM lookup always resolves to the freshest kernel-6.1 x86_64 AL2023. `terraform plan` will show an AMI change any time AWS rebases (~monthly) — not a real diff, since `aws_instance` doesn't replace on AMI change unless the ID field is actually written back. |

### No SSH ingress

| Area | Decision |
|---|---|
| Choice | Port 22 not opened in the EC2 SG. |
| Why | SSM Session Manager (via `AmazonSSMManagedInstanceCore` on the instance role) provides shell access without ever opening a public port. All connections auth via IAM + are logged to CloudTrail. Removes an entire attack surface (SSH brute-force scanners) at zero UX cost. |

### user_data as bash, not cloud-init YAML

| Area | Decision |
|---|---|
| Choice | Single Bash script rendered via `templatefile()`. |
| Why | The script is ~80 lines and mostly linear; cloud-init YAML would fragment the logic across `runcmd`/`write_files`/etc. with no gain. Bash `set -euxo pipefail` gives clear failure semantics; output tees to `/var/log/user-data.log` for post-mortem. Simpler mental model. |

### All Django env vars in SSM, not just secrets

| Area | Decision |
|---|---|
| Choice | Both SecureString (DJANGO_SECRET_KEY, DB_PASSWORD) and String (DB_HOST, DB_NAME, DB_USER, DB_PORT, DOMAIN, ALLOWED_HOSTS, AWS_STORAGE_BUCKET_NAME, AWS_STATIC_BUCKET_NAME, AWS_REGION) in SSM. |
| Why | One source of truth for env config; one `aws ssm get-parameters-by-path` call retrieves everything; one shape of Terraform resource to add/rotate any var. Standard params are free, SecureString params are free (both up to 10k in standard tier). Rotation of any value = one `put-parameter` + gunicorn restart. |
| SSM path | `/wedding-site/prod/<VAR_NAME>`. `prod` in the path leaves room for `/wedding-site/dev/` if we ever want a staging env. |

### random_password for DJANGO_SECRET_KEY

| Area | Decision |
|---|---|
| Choice | `resource "random_password" "django_secret_key"` with `length = 50`, `override_special = "!@#$%*-_=+"`. Value pushed straight to the SSM SecureString param. |
| Why | No manual generation, no risk of a weak key, no laptop involvement. Terraform state stores the value (encrypted-at-rest per state backend config; still local this session), but the "public copy" lives in KMS-encrypted SSM. If we ever want to rotate: `terraform apply -replace=random_password.django_secret_key` + gunicorn restart. |
| Trade-off | Terraform state now has a sensitive value. Not a new problem — the DB master password was already there from Session 11. State stays local + gitignored. |

### `random_password` and `ssm` need new provider (random)

| Area | Decision |
|---|---|
| Choice | Add `hashicorp/random` to `main.tf` `required_providers`. Pin an exact version. |
| Why | `random_password` isn't in `hashicorp/aws`. `random` is the canonical provider for this. Version pin per [[feedback-strict-version-pins]]. |

### Ruff config at repo root, not backend/

| Area | Decision |
|---|---|
| Choice | `pyproject.toml` at repo root. |
| Why | Ruff auto-discovers by walking up from CWD; putting it at the root means both `ruff check backend/` and `ruff check .` work identically. Also, `pyproject.toml` at root is a common convention even without a Python package there. |
| Config | `line-length = 100`, `target-version = "py312"`, `select = ["E", "F", "W", "I", "UP", "B", "SIM"]`. Per-file ignores: `backend/**/migrations/**` (auto-generated) all rules off; `backend/**/tests.py` allow long lines + unused imports (fixture setup). |
| Format | Use `ruff format` (drop-in Black replacement). CI checks with `ruff format --check`. |

### CI on push (any branch) + PR — no branch filter

| Area | Decision |
|---|---|
| Choice | `on: { push: {}, pull_request: {} }` with no branch filter. |
| Why | Fast feedback on feature branches without needing to open a PR. Solo project — no CI-minute worries. When branch protection lands Session 13, this same workflow becomes the "required check." |

### Node 20 + pnpm 11.17.0 on EC2 (matches local)

| Area | Decision |
|---|---|
| Choice | `dnf install nodejs20` (AL2023 provides Node 20 in default repos), then `corepack enable && corepack prepare pnpm@11.17.0 --activate`. |
| Why | Matches `frontend/package.json`'s `packageManager` pin. Building frontend on-instance is ~1 min at first boot and each deploy; acceptable overhead. Alternative (build in CI, rsync artifacts) is Session 14 concern once the deploy workflow exists. |

### Out-of-scope defer log

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Photo alt-text values** — still pending.
- **CloudFront + DNS cutover + phase 0 destroy** — Session 13.
- **`SECURE_PROXY_SSL_HEADER` + `CSRF_TRUSTED_ORIGINS` + `SECURE_SSL_REDIRECT`** — Session 13 (needs CloudFront to be sensible).
- **CloudWatch Agent + log groups + retention + ERROR alarm** — Session 14.
- **GitHub Actions OIDC + `deploy.yml`** — Session 14.
- **Branch protection on `main`** — Session 13.
- **`django-vite`** — still deferred.
- **Real gallery page** — Session 13+.
- **`cost-guard` and `wedding-copy-editor` subagents** — Phase 3 tail.

---

## Progress

- [x] Session log created (this file).
- [x] `ssm.tf` written (random_password + 2 SecureString + 9 String params, all under `/wedding-site/prod/`).
- [x] `variables.tf` extended with `domain_name` (required); `terraform.tfvars.example` updated.
- [x] `main.tf` extended with `hashicorp/random 3.7.2` provider pin.
- [x] `ec2_iam.tf` written (trust policy, S3 policy attach, SSM read policy with KMS decrypt condition, AmazonSSMManagedInstanceCore attach, instance profile).
- [x] `security_groups.tf` extended with 80 + 443 ingress rules on ec2 SG (no SSH).
- [x] `templates/user_data.sh.tftpl` written — uses jq for SSM→.env rendering; installs Python 3.12 + Node 20 + pnpm + nginx + git + jq; clones repo; pnpm build; migrate; collectstatic; writes systemd unit + nginx conf; starts services.
- [x] `templates/gunicorn.service.tftpl` — `Type=simple` (not notify — no gunicorn[systemd] pin), 3 workers, unix socket, journal logs.
- [x] `templates/nginx-site.conf.tftpl` — proxy_pass to gunicorn unix socket; no /static/ or /media/ handling (those come from S3 directly via django-storages).
- [ ] **`ec2.tf` NOT YET WRITTEN** — AMI SSM data source + `aws_instance.web` + `aws_eip.web` + `aws_eip_association.web`. This is the biggest remaining chunk; see Pickup below.
- [ ] `outputs.tf` NOT YET extended with EC2 outputs.
- [ ] `production.py` NOT YET extended for `ALLOWED_HOSTS` env-list.
- [ ] `pyproject.toml` NOT YET written; ruff NOT YET pinned in local.txt.
- [ ] Ruff NOT YET run against backend/.
- [ ] `.github/workflows/ci.yml` NOT YET written.
- [ ] `terraform validate` + `fmt -diff` + non-ASCII grep NOT YET run.
- [ ] Full test suite + new ALLOWED_HOSTS test NOT YET run.
- [ ] User runs `terraform plan -out=tfplan` + `apply` — pending.
- [ ] `curl http://<eip>/` verification — pending.
- [ ] Session log finalized — pending.

### Digressions worth remembering

**gunicorn systemd unit needs `Type=simple`, not `Type=notify`.** First
draft of `templates/gunicorn.service.tftpl` used `Type=notify`, which
requires `pip install gunicorn[systemd]` (the sd-notify extra). Our
`requirements/production.txt` pins plain `gunicorn==26.0.0`, so systemd
would hang waiting for a `READY=1` signal that never arrives. Fix: drop
the `Type=notify` line (defaults to `Type=simple` — systemd considers
the service started once the ExecStart process forks). If we ever want
proper notify semantics, add `gunicorn[systemd]` to production.txt and
switch back. `Type=simple` means nginx may briefly 502 if it starts
before gunicorn binds the socket; user_data sleeps 2s before the
sanity-check curl, and after that both services are steady-state.

**Nested-heredoc quoting hazards in user_data.** First user_data draft
used `sudo -u ec2-user -H bash <<EOSU ... EOSU` nested blocks with
`\$var` escapes to defer shell expansion to the inner bash. Fragile.
Rewrote to stage a helper script at `/tmp/bootstrap-app.sh` and invoke
via `runuser -u ec2-user -- /tmp/bootstrap-app.sh "$APP_DIR" ...`. Args
pass positionally, no escape gymnastics. Also switched .env rendering
from `python3.12 -c '...'` (blocked by "can't nest single quotes in
bash single-quoted string") to `jq -r '... | @sh'` which shell-quotes
values correctly for `set -a; . .env` consumption. jq added to the dnf
install list.

**AL2023 stock nginx.conf has a default `server` block on port 80.**
Would conflict with ours (both `default_server`). user_data comments
the default block out with `sed -i.bak '/^\s*server\s*{/,/^\s*}/ s/^/# /'`.
Not the cleanest — the sed regex assumes indentation matches AL2023's
default; if AWS changes the stock config formatting, this breaks. If we
see nginx failing to start with "duplicate default_server" after any
AMI rebase, revisit.

---

## PICKUP FOR NEXT TERMINAL SESSION

**Session limit hit mid-Session-12.** Next terminal should read this
file top-to-bottom, then continue from here. Nothing has been applied
to AWS this session — all local file writes only. Terraform state is
still at Session 11 (18 resources).

### What's already written and on disk

Under `infra/phase3/`:
- `main.tf` — provider pins including new `random 3.7.2`
- `variables.tf` — `domain_name` added (required)
- `terraform.tfvars.example` — `domain_name` placeholder added
- `ssm.tf` — `random_password.django_secret_key` + 11 `aws_ssm_parameter` resources
- `ec2_iam.tf` — role, 3 policies, instance profile
- `security_groups.tf` — 80 + 443 ingress rules appended
- `templates/user_data.sh.tftpl` — full bootstrap script
- `templates/gunicorn.service.tftpl` — systemd unit
- `templates/nginx-site.conf.tftpl` — reverse proxy config

### Immediate next step — write `ec2.tf`

```hcl
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
}

resource "aws_eip" "web" {
  domain = "vpc"
  tags   = { Name = "${var.project_tag}-web-eip" }
}

resource "aws_instance" "web" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  user_data = templatefile("${path.module}/templates/user_data.sh.tftpl", {
    app_dir          = "/home/ec2-user/aws-wedding-website"
    repo_url         = "https://github.com/stnielse/aws-wedding-website.git"
    ssm_prefix       = local.ssm_prefix
    aws_region       = "us-east-1"
    gunicorn_service = templatefile("${path.module}/templates/gunicorn.service.tftpl", {
      app_dir = "/home/ec2-user/aws-wedding-website"
    })
    nginx_conf = file("${path.module}/templates/nginx-site.conf.tftpl")
  })
  user_data_replace_on_change = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"  # IMDSv2 required
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = { Name = "${var.project_tag}-web" }

  depends_on = [
    aws_db_instance.wedding,  # RDS reachable before user_data runs migrate
    aws_ssm_parameter.django_secret_key,
    aws_ssm_parameter.db_password,
    aws_ssm_parameter.db_host,
    aws_ssm_parameter.db_port,
    aws_ssm_parameter.db_name,
    aws_ssm_parameter.db_user,
    aws_ssm_parameter.domain,
    aws_ssm_parameter.allowed_hosts,
    aws_ssm_parameter.aws_region,
    aws_ssm_parameter.aws_storage_bucket_name,
    aws_ssm_parameter.aws_static_bucket_name,
  ]
}

resource "aws_eip_association" "web" {
  instance_id   = aws_instance.web.id
  allocation_id = aws_eip.web.id
}
```

**Watch out** — `aws_ssm_parameter.allowed_hosts` in `ssm.tf` references
`aws_eip.web.public_ip`, creating a cycle with the `depends_on` above.
Terraform resolves this: the EIP resource has no explicit dependency on
the instance (association is a separate resource), so ssm→eip→instance
is fine. But re-verify with `terraform plan` before apply.

### Remaining task list (numeric IDs may have shifted; the work is what matters)

1. **Write `infra/phase3/ec2.tf`** (see above).
2. **Extend `infra/phase3/outputs.tf`** with `ec2_instance_id`,
   `ec2_public_ip = aws_eip.web.public_ip`, `ec2_public_dns =
   aws_instance.web.public_dns`, `ec2_iam_role_arn = aws_iam_role.ec2.arn`,
   `ssm_parameter_prefix = local.ssm_prefix`.
3. **Extend `backend/config/settings/production.py`** — parse
   `ALLOWED_HOSTS` as comma-separated env var:
   ```python
   ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', os.environ['DOMAIN']).split(',') if h.strip()]
   ```
   Add a test in `backend/config/tests.py` under a new
   `AllowedHostsParsingTests(SimpleTestCase)` that stubs the env var
   and re-imports settings (or just tests the split logic directly).
4. **Create `pyproject.toml` at repo root** with `[tool.ruff]`:
   ```toml
   [tool.ruff]
   line-length = 100
   target-version = "py312"
   extend-exclude = ["backend/**/migrations/**"]

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "UP", "B", "SIM"]

   [tool.ruff.lint.per-file-ignores]
   "backend/**/tests.py" = ["E501"]  # long assertion strings OK
   ```
5. **Pin ruff** in `backend/requirements/local.txt` — latest is `ruff==0.14.4`
   (or check `pip index versions ruff` for current). Install:
   `.venv/bin/pip install ruff==<version>`.
6. **Run `ruff check backend/`** — fix any real issues. Expect a handful
   of `I001` (import sorting) and maybe `UP` upgrades on older code.
   Then `ruff format backend/` for whitespace normalization. Commit the
   fixes as a distinct commit before continuing.
7. **Write `.github/workflows/ci.yml`** — two parallel jobs:
   - `python`: setup-python 3.12, `pip install -r backend/requirements/production.txt
     -r backend/requirements/local.txt`, `ruff check backend/`,
     `ruff format --check backend/`, `cd backend && python manage.py test`.
   - `frontend`: setup-node 20, `corepack enable`, `cd frontend && pnpm install
     --frozen-lockfile && pnpm lint && pnpm build`.
   - `on: { push: {}, pull_request: {} }` — no branch filter.
8. **`terraform -chdir=infra/phase3 validate`** + `fmt -diff` + non-ASCII
   grep (`grep -RnP '[^\x00-\x7F]' *.tf` — verify no `description = "..."`
   fields have em-dashes/etc. per the ASCII-only memory).
9. **Run full test suite** — must pass, target ≥45 tests.
10. **Hand `terraform plan -out=tfplan` + `apply` to the user.** Expect
    ~20-25 new resources: 11 SSM params + IAM role/profile/policies (5-6) +
    2 SG ingress rules + AMI data source + EIP + instance + EIP association.
    Instance boots ~1 min; user_data ~5-8 min (dnf update + pnpm install
    + collectstatic to S3 dominate). Terraform doesn't wait for user_data
    to finish — the apply returns as soon as the instance is `running`.
    User verifies via SSM Session Manager: `aws ssm start-session --target
    <instance-id>`, then `tail -f /var/log/user-data.log` until `=== user_data done ===`.
11. **Verify `curl -s -o /dev/null -w '%{http_code}\n' http://<eip>/`** returns
    200 (or a Django-served 4xx — anything but 5xx / timeout means the stack
    is up).
12. **Finalize this log** — flip remaining `[ ]` to `[x]`, fill in real
    EIP + instance ID in the digressions, capture any surprises.

### If something breaks

- **user_data failed silently** → SSM to the instance, `sudo cat /var/log/user-data.log`. `set -x` should show the exact line that failed.
- **gunicorn won't start** → `sudo journalctl -u gunicorn -n 100`. Common causes: bad .env (missing var, unescaped char), venv path wrong, migrations pending.
- **nginx won't start** → `sudo nginx -t` for config test. If duplicate default_server, the sed didn't neutralize the stock block — hand-edit `/etc/nginx/nginx.conf`.
- **RDS unreachable from EC2** → confirm EC2 SG in the RDS SG's ingress (via `aws_vpc_security_group_ingress_rule.rds_from_ec2` from Session 11); test with `pg_isready -h <db_address> -p 5432` from the instance (postgresql17 client installed).
- **SSM params can't be read by the instance** → check the IAM role's `ec2_ssm_read` policy is attached; test with `aws ssm get-parameter --name /wedding-site/prod/DB_HOST --with-decryption` from the instance.

### Git state at pickup

User commits incrementally throughout the session, not just at end. All
Session 10 + 11 + in-progress Session 12 work will be committed before
the next terminal picks up. Expect a **clean tree** (`git status` shows
"nothing to commit, working tree clean") when Session 12 resumes.

Recent commit log will show Session 10 + 11 in full, plus whatever
partial Session 12 commits landed (SSM/IAM/SG/templates all done as of
this write). Confirm with `git log --oneline -15` at pickup.

Git write ops remain user-owned per [[feedback-git-operations]]; do NOT
stage or commit anything on their behalf during pickup.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-02-session-12-phase3-ec2-and-ci.md` — this log
- `infra/phase3/ssm.tf`
- `infra/phase3/ec2_iam.tf`
- `infra/phase3/ec2.tf`
- `infra/phase3/templates/user_data.sh.tftpl`
- `infra/phase3/templates/gunicorn.service.tftpl`
- `infra/phase3/templates/nginx-site.conf.tftpl`
- `pyproject.toml` — ruff config
- `.github/workflows/ci.yml`

**Modified:**
- `infra/phase3/main.tf` — add `hashicorp/random` provider pin
- `infra/phase3/security_groups.tf` — 80 + 443 ingress rules
- `infra/phase3/outputs.tf` — EC2 outputs
- `infra/phase3/README.md` — Session 12 additions
- `backend/config/settings/production.py` — ALLOWED_HOSTS env-list parsing
- `backend/config/tests.py` (or new test file) — ALLOWED_HOSTS test
- `backend/requirements/local.txt` — pin ruff

Per working contract, all `git add` / `git commit` is left to the user.

## Session 13 handoff

Session 13 does the public-facing cutover. Prep list:

1. **CloudFront distribution** in `infra/phase3/cloudfront.tf`:
   - Three origins: media bucket, static bucket, EC2 EIP.
   - Cache behaviors: `/media/*` → media origin, `/static/*` → static
     origin, default → EC2 origin.
   - OAC for the two S3 origins.
   - Custom domain aliases: apex + www.
   - ACM cert ARN from the phase 0 tfvars (still Issued in us-east-1).
   - Custom error pages (403 → maintenance-esque page? or just pass
     through — decide during Session 13).
2. **Bucket policies uncommented** in `s3_media.tf` and `s3_static.tf`
   — `AllowCloudFrontOACRead` scoped to the distribution ARN. Wire via
   `aws_s3_bucket_policy` resources (currently commented placeholders).
3. **`production.py` — CloudFront-aware settings:**
   - `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
   - `CSRF_TRUSTED_ORIGINS = [f'https://{domain}', f'https://www.{domain}']`
   - `SECURE_SSL_REDIRECT = False` — leave CloudFront to enforce
     redirect-to-https at the edge, not Django (avoids double-redirect
     loops).
   - `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`.
   - Push updated SSM params (`AWS_S3_CUSTOM_DOMAIN`,
     `AWS_STATIC_CUSTOM_DOMAIN` — the CloudFront domain names).
4. **Route 53 cutover:**
   - Both `apex_a` and `www_a` alias records in `infra/phase0/route53.tf`
     will need to swap. Two paths:
     - **A. Move the records to `infra/phase3/route53.tf`** — cleaner,
       requires `terraform state mv` between modules or a re-import.
     - **B. Delete records in phase 0, create in phase 3** — brief
       DNS outage (seconds) while apply runs.
     - Recommend A. Deferred detailed decision to Session 13.
5. **Phase 0 destroy:**
   - Once CloudFront + DNS are live and healthy, `cd infra/phase0 &&
     terraform destroy`. Update `phase0/README.md` marking it retired.
   - CloudFront distribution disable + delete takes 15-30 minutes;
     Terraform handles both. Route 53 record removal is instant.
6. **Branch protection on `main`:**
   - GitHub Settings → Branches → Add rule for `main`:
     - Require PR before merging.
     - Require status checks: `ci / python`, `ci / frontend`.
     - Require conversation resolution.
     - No direct pushes (except by admins in emergencies).
7. **First real PR** flow tested — user opens a PR from a feature
   branch, CI runs, merge triggers... nothing yet (deploy is Session 14).

**Cost after Session 13:** +CloudFront (free tier covers wedding-site
traffic; ~$0.09/mo beyond that unlikely). Phase 0 destroy saves nothing
(< $0.10/mo). Net site cost stays ~$25/mo.

Before touching anything in Session 13:

- Read this file (Session 12), plus Session 11's RDS notes.
- **Python:** `/Users/stevennielsen/aws-wedding-website/.venv/bin/python`.
- **Frontend:** `pnpm` via corepack from `frontend/`.
- **Runserver:** 8765. **Vite dev:** `http://localhost:5175/`.
- Every direct Terraform provider / module version gets exact-pinned per [[feedback-strict-version-pins]].
- Long-running `terraform apply` / `destroy` handed to the user per [[feedback-long-running-commands]].
- Grep for non-ASCII in TF `description` fields before any apply per [[feedback-aws-ascii-only-descriptions]].
- `awscrt` in the venv from Session 10 for boto3+SSO per [[user-aws-sso-auth]].

## Open questions / follow-ups

- **Q1 dietary + Q6 schedule** — still open from Session 7.
- **Photo alt-text values** — final copy still pending.
- **Deletion protection on RDS** — flip to true closer to the wedding?
- **User's home IP `/32`** — moot; no SSH, SSM only.
- **`<picture>` mobile crop** for hero — Session 13+.
- **`django-vite`** — still deferred.
- **Real gallery page** — Session 13+.
- **Frontend build on EC2 vs CI-shipped artifacts** — building on-instance
  is fine for now; Session 14's `deploy.yml` may switch to
  CI-build-then-rsync for faster deploys.
- **`SECURE_HSTS_*`** — worth setting once we're on stable HTTPS;
  probably Session 13 or a Session 15 hardening pass.
