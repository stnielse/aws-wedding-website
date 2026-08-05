# infra/phase0 — RETIRED 2026-08-05

**Status:** destroyed. Session 14 (2026-08-05) landed the phase 3
CloudFront distribution + DNS cutover, then ran `terraform destroy` on
this module. No AWS resources here anymore.

This directory is preserved for historical reference (Sessions 2–3 built
it, Sessions 4–13 kept it running) and because the module structure is a
useful worked example for future one-shot Terraform modules. Do **not**
run `terraform apply` here — the CloudFront alias config in `cloudfront.tf`
still names apex + www, which are now owned by
`infra/phase3/cloudfront.tf`. A re-apply would collide.

## Historical scope

Phase 0 maintenance page. Served a static "under construction" HTML at the
apex domain and `www.<domain>` over HTTPS via CloudFront, backed by a private
S3 bucket (OAC-restricted). Any path a visitor tried mapped to the same page
via CloudFront custom error responses.

The module was intentionally standalone — it was destroyed when Phase 3
came online in Session 14, so the phase 3 CloudFront distribution got
created fresh instead of being extended in place.

## Prereqs

- Terraform installed. On macOS: `brew tap hashicorp/tap && brew install hashicorp/tap/terraform`.
- AWS credentials that can create S3 buckets, CloudFront distributions, and Route 53 records. Use the IAM admin user, not root.
- ACM cert (us-east-1) covering `<domain>` and `www.<domain>`, status Issued.
- Route 53 hosted zone for `<domain>` already exists.

## First apply

```sh
cd infra/phase0
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: domain_name, acm_certificate_arn, hosted_zone_id

terraform init
terraform plan -out=tfplan   # review — should be 11 resources
terraform apply "tfplan"     # applies exactly the reviewed plan
rm tfplan                    # the plan file has no reuse value after apply
```

Using `plan -out=<file>` + `apply <file>` (instead of a plain `terraform
apply`, which re-plans against current state) guarantees the actions
executed are exactly the ones reviewed — no drift between plan and apply if
something in the real world changes in the intervening seconds. Habit-form
it locally so the same workflow translates to CI later (plan job → human
approval → apply job on the saved artifact).

The plan file is a binary blob (view with `terraform show tfplan`) that can
embed sensitive input values, so it's gitignored (`infra/**/tfplan`).

CloudFront deployment takes 10-20 minutes; `apply` blocks until the
distribution is `Deployed`. DNS propagation is usually seconds because both
apex and www use Route 53 alias records inside the same zone.

## Verification

```sh
DOMAIN=$(terraform output -raw cloudfront_domain_name)   # d1234.cloudfront.net

# Replace <domain> with your apex domain below.
curl -sI https://<domain>              | head -1   # HTTP/2 200
curl -sI http://<domain>               | head -1   # HTTP/1.1 301 (redirect to https)
curl -sI https://www.<domain>          | head -1   # HTTP/2 200
curl -sI https://<domain>/anything     | head -1   # HTTP/2 200  (custom error response)

# S3 must not be directly reachable.
BUCKET=$(terraform output -raw bucket_name)
curl -sI https://${BUCKET}.s3.amazonaws.com/index.html | head -1   # HTTP/1.1 403
```

Then open the apex and `www` in a browser and confirm the page renders
legibly on desktop and mobile widths.

## Updating the maintenance HTML

Edit `maintenance/index.html`, then:

```sh
terraform plan -out=tfplan   # confirm only the S3 object changes
terraform apply "tfplan"     # re-uploads the object (etag = filemd5)
rm tfplan

# CloudFront caches for 24h by default. Invalidate to see the change now.
aws cloudfront create-invalidation \
  --distribution-id "$(terraform output -raw cloudfront_distribution_id)" \
  --paths '/index.html' '/'
```

## Teardown (already executed)

```sh
terraform destroy
```

Executed 2026-08-05 as part of Session 14, after phase 3's CloudFront +
DNS cutover was verified live. Everything the module created is gone,
including the bucket contents (`force_destroy = true`). CloudFront
disable+delete took ~20 minutes.

`terraform.tfstate*` files remain on disk (local, gitignored) as an
audit trail — delete them by hand if you want zero trace.

## Cost estimate

At near-zero traffic (this page shouldn't be found until we start sharing
the URL):

- S3: fractions of a cent — one 2 KB object, negligible requests.
- CloudFront: fractions of a cent — free tier covers 1 TB/month egress and 10M requests.
- Route 53: hosted zone is $0.50/mo (already existed pre-Phase-0). Alias
  queries are free.

Expected monthly cost of the Phase 0 module itself: **< $0.10** unless the
page gets meaningful traffic.

## Files

| File | Purpose |
|---|---|
| `main.tf` | Terraform + AWS provider version pins, `default_tags`. |
| `variables.tf` | `domain_name`, `acm_certificate_arn`, `hosted_zone_id`, `project_tag`. |
| `s3.tf` | Private bucket, public-access block, OAC bucket policy, `index.html` object. |
| `cloudfront.tf` | OAC + distribution with ACM cert, custom 403/404 → 200 responses, HTTPS-only. |
| `route53.tf` | A + AAAA alias records for apex and www. |
| `outputs.tf` | `bucket_name`, `cloudfront_distribution_id`, `cloudfront_domain_name`. |
| `maintenance/index.html` | The static page — self-contained, inline CSS. |
| `terraform.tfvars.example` | Committed placeholder for the real `terraform.tfvars` (gitignored). |
