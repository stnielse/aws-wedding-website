# infra/phase3

Phase 3 opener — two S3 buckets (media + static) and an IAM policy document
scoped to them. No CloudFront, no Route 53 changes, no compute. Meant to
coexist with `infra/phase0/` while the maintenance page keeps serving the
public domain; the CloudFront distribution + DNS cutover + phase 0 teardown
land in a later phase 3 session.

**What this module creates:**

- `${project_tag}-media-<accountid>` — private S3 bucket for MEDIA_URL
  uploads (versioned; non-current versions expire after 90 days;
  `force_destroy = false`).
- `${project_tag}-static-<accountid>` — private S3 bucket for
  `collectstatic` output (not versioned; `force_destroy = true`).
- IAM policy document (data source only) granting an EC2 instance role
  read/write on both bucket contents, list on both bucket roots. Emitted
  as an output for a future session to attach.

**What it does NOT create yet:** CloudFront distribution, Route 53 records,
bucket policies (bucket access is IAM-only until CloudFront exists).

## Prereqs

- Terraform installed (`brew install hashicorp/tap/terraform`), version
  `1.15.8` per `main.tf`.
- AWS credentials that can create S3 buckets and read IAM. Use the IAM
  admin user, not root.
- The `phase0/` module can stay applied — the two modules don't share any
  state or resources.

## First apply

```sh
cd infra/phase3
cp terraform.tfvars.example terraform.tfvars   # optional; defaults are fine

terraform init
terraform plan -out=tfplan   # expect ~9 resources
terraform apply "tfplan"
rm tfplan
```

The apply is fast — S3 buckets create in seconds, no CloudFront wait.

Capture the outputs for the local verification step:

```sh
terraform output media_bucket_name
terraform output static_bucket_name
```

## Verification (local Django against real S3)

1. Copy an `.env` into `backend/` (gitignored) with the two bucket names
   and AWS region:

   ```sh
   DJANGO_SECRET_KEY=verify-only-not-prod-safe
   DOMAIN=localhost
   DB_NAME=... DB_USER=... DB_PASSWORD=... DB_HOST=127.0.0.1
   AWS_STORAGE_BUCKET_NAME=<media_bucket_name>
   AWS_STATIC_BUCKET_NAME=<static_bucket_name>
   AWS_REGION=us-east-1
   ```

2. Run `collectstatic` against production settings. The hashed static tree
   should land in the static bucket:

   ```sh
   cd backend
   ../.venv/bin/python manage.py collectstatic \
       --settings=config.settings.production --noinput
   aws s3 ls "s3://$(cd ../infra/phase3 && terraform output -raw static_bucket_name)/" \
       --recursive | head
   ```

3. Start `runserver` under production settings and upload a `Photo` via
   `/admin/`. Confirm the object lands in the media bucket:

   ```sh
   aws s3 ls "s3://$(cd ../infra/phase3 && terraform output -raw media_bucket_name)/gallery/"
   ```

4. Neither bucket should be reachable without IAM auth:

   ```sh
   curl -sI "https://$(terraform output -raw media_bucket_name).s3.amazonaws.com/" | head -1
   # HTTP/1.1 403
   ```

Delete the scratch `.env` after verification — the wired-up prod `.env`
comes later, on EC2.

## Teardown

```sh
terraform destroy
```

The media bucket has `force_destroy = false`, so if it contains objects,
`destroy` will refuse the S3 bucket delete step. Empty it first:

```sh
aws s3 rm "s3://$(terraform output -raw media_bucket_name)/" --recursive
aws s3api delete-objects --bucket "$(terraform output -raw media_bucket_name)" \
    --delete "$(aws s3api list-object-versions \
                  --bucket "$(terraform output -raw media_bucket_name)" \
                  --output=json \
                  --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}')" 2>/dev/null || true
terraform destroy
```

(The version-delete step handles the versioned bucket. If you never
uploaded anything, the plain `aws s3 rm` is enough.)

## Cost estimate

At Phase 3 opener scope (no CDN, no compute):

- S3 storage: fractions of a cent per GB-month. Wedding photos might total
  ~1 GB eventually — call it $0.025/month.
- S3 requests: negligible during verification, near-zero during idle.
- IAM: free.

Expected monthly cost of this module alone: **< $0.10** until compute lands.

## Files

| File | Purpose |
|---|---|
| `main.tf` | Provider pins, `default_tags`, `aws_caller_identity` data source. |
| `variables.tf` | `project_tag`. |
| `s3_media.tf` | Media bucket, ownership, PAB, versioning, lifecycle. |
| `s3_static.tf` | Static bucket, ownership, PAB. |
| `iam.tf` | `data "aws_iam_policy_document" "ec2_s3"`. |
| `outputs.tf` | Bucket names, ARNs, regional domain names, policy JSON. |
| `terraform.tfvars.example` | Committed placeholder for the gitignored `terraform.tfvars`. |
