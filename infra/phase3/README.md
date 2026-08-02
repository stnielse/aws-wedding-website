# infra/phase3

Phase 3 — S3 buckets (Session 10) + VPC and RDS Postgres (Session 11).
Coexists with `infra/phase0/` while the maintenance page keeps serving
the public domain; CloudFront + DNS cutover + phase 0 teardown land in
Session 12+.

**What this module creates:**

Session 10 (S3 + IAM):

- `${project_tag}-media-<accountid>` — private S3 bucket for MEDIA_URL
  uploads (versioned; non-current versions expire after 90 days;
  `force_destroy = false`).
- `${project_tag}-static-<accountid>` — private S3 bucket for
  `collectstatic` output (not versioned; `force_destroy = true`).
- IAM policy document (data source only) granting an EC2 instance role
  read/write on both bucket contents, list on both bucket roots. Emitted
  as an output for Session 12 to attach.

Session 11 (network + DB):

- VPC 10.0.0.0/16 with DNS hostnames enabled.
- Public subnet 10.0.1.0/24 in `us-east-1a` (Session 12 EC2 lives here),
  private subnets 10.0.11.0/24 and 10.0.12.0/24 (in `us-east-1a` and
  `us-east-1b` — the second AZ purely to satisfy RDS subnet-group
  requirements).
- Internet Gateway + public route table with default route to it. Private
  route table has no default route; no NAT gateway.
- Two security groups: `ec2` (empty placeholder; Session 12 adds 80/443
  ingress) and `rds` (5432 inbound from `ec2` SG only).
- RDS Postgres 17.10 on `db.t3.micro`, 20 GB gp3, encrypted at rest, backup
  retention 7 days, PostgreSQL log export to CloudWatch (30-day retention),
  deletion_protection false, skip_final_snapshot true.

**What it does NOT create yet:** CloudFront distribution, Route 53 records,
bucket policies, EC2, IAM role attachment. All Session 12+.

## Prereqs

- Terraform installed (`brew install hashicorp/tap/terraform`), version
  `1.15.8` per `main.tf`.
- AWS credentials that can create VPC / EC2-network / RDS / S3 / IAM. Use
  the IAM admin user, not root.
- For Python-side verification: `pip install awscrt` into `.venv/`
  (SSO login needs it).
- The `phase0/` module can stay applied — the two modules don't share any
  state or resources.

## First apply — Session 10 (S3)

```sh
cd infra/phase3
cp terraform.tfvars.example terraform.tfvars   # set db_master_password below

terraform init
terraform plan -out=tfplan   # Session 10 alone: 8 resources
terraform apply "tfplan"
rm tfplan
```

## First apply — Session 11 (VPC + RDS)

Set `db_master_password` in `terraform.tfvars` before applying — the
variable is `sensitive` (no default; plan fails without it).

```sh
terraform plan -out=tfplan   # Session 11 additions: ~15 more resources
terraform apply "tfplan"     # RDS provisioning ~5-10 minutes
rm tfplan
```

Capture the outputs Session 12 will feed into the EC2 `.env`:

```sh
terraform output db_endpoint
terraform output db_address
terraform output db_name
terraform output db_master_username
terraform output media_bucket_name
terraform output static_bucket_name
```

## Verification (S3 — Session 10)

Small scratch-write proof. Uses production settings against the real
buckets; two 25-byte files, cleaned up after.

```sh
cd ../../backend

DJANGO_SECRET_KEY=verify-not-prod DOMAIN=localhost \
DB_NAME=stub DB_USER=stub DB_PASSWORD=stub DB_HOST=stub \
AWS_STORAGE_BUCKET_NAME=$(cd ../infra/phase3 && terraform output -raw media_bucket_name) \
AWS_STATIC_BUCKET_NAME=$(cd ../infra/phase3 && terraform output -raw static_bucket_name) \
AWS_REGION=us-east-1 \
../.venv/bin/python -c "
import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'
django.setup()
from django.core.files.storage import default_storage, storages
from django.core.files.base import ContentFile
default_storage.save('gallery/verify.txt', ContentFile(b'ok'))
storages['staticfiles'].save('verify.txt', ContentFile(b'ok'))
print('wrote to both buckets')
"

# Cleanup after:
aws s3 rm "s3://$(cd ../infra/phase3 && terraform output -raw media_bucket_name)/gallery/verify.txt"
aws s3 rm "s3://$(cd ../infra/phase3 && terraform output -raw static_bucket_name)/verify.txt"
```

Neither bucket should be reachable without IAM auth:

```sh
curl -sI "https://$(terraform output -raw media_bucket_name).s3.amazonaws.com/" | head -1
# HTTP/1.1 403
```

## Verification (RDS — Session 11)

RDS is in a private subnet, unreachable from a laptop. You can confirm
provisioning by:

```sh
aws rds describe-db-instances \
    --db-instance-identifier "$(terraform output -raw db_endpoint | cut -d. -f1)" \
    --query 'DBInstances[0].[DBInstanceStatus,Engine,EngineVersion,PubliclyAccessible]' \
    --output text
# should be:   available   postgres   17.10   False
```

Actual DB connectivity is tested from EC2 in Session 12 (first
`manage.py migrate` is the end-to-end proof).

## Teardown

The media bucket has `force_destroy = false`, so if it contains objects,
`destroy` will refuse the S3 bucket delete step. Empty it first (see
the S3 verification section for the version-aware delete).

RDS teardown is quick because `skip_final_snapshot = true` and
`deletion_protection = false`. If either is flipped for pre-wedding
hardening, `terraform destroy` will refuse — reverse those first with a
`plan/apply` before destroying.

```sh
terraform destroy   # ~5-8 min for RDS delete
```

## Cost estimate

At Phase 3 middle scope (S3 + VPC + RDS, no CDN, no compute):

- **S3:** fractions of a cent per GB-month. Wedding photos ~1 GB eventually
  → $0.025/mo.
- **VPC / IGW / SGs / route tables:** free.
- **RDS db.t3.micro** (single-AZ, 20 GB gp3): ~$13/mo instance + ~$2/mo
  storage.
- **CloudWatch logs** (RDS postgresql stream, 30-day retention): fractions
  at wedding-site traffic.

Expected monthly cost after Session 11 apply: **~$15/mo**. Session 12
adds EC2 (~$5-7.50/mo) + CloudFront (free tier), landing the full site
around **~$25/mo**.

## Files

Session 10:

| File | Purpose |
|---|---|
| `main.tf` | Provider pins, `default_tags`, `aws_caller_identity` data source. |
| `variables.tf` | `project_tag`, DB vars. |
| `s3_media.tf` | Media bucket, ownership, PAB, versioning, lifecycle. |
| `s3_static.tf` | Static bucket, ownership, PAB. |
| `iam.tf` | `data "aws_iam_policy_document" "ec2_s3"`. |

Session 11:

| File | Purpose |
|---|---|
| `vpc.tf` | VPC + 3 subnets + IGW + route tables + associations. |
| `security_groups.tf` | EC2 placeholder SG + RDS SG (5432 from EC2). |
| `rds.tf` | Subnet group + Postgres 17.10 instance + CloudWatch log group. |

Shared:

| File | Purpose |
|---|---|
| `outputs.tf` | Bucket names, ARNs, S3 policy JSON, VPC/subnet IDs, SG IDs, DB endpoint. |
| `terraform.tfvars.example` | Committed placeholder; `db_master_password` REQUIRED in the gitignored real file. |
