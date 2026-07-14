# infra/phase0

Phase 0 maintenance page. Serves a static "under construction" HTML at the
apex domain and `www.<domain>` over HTTPS via CloudFront, backed by a private
S3 bucket (OAC-restricted). Any path a visitor tries maps to the same page
via CloudFront custom error responses.

This module is intentionally standalone — it gets destroyed when Phase 3 (the
main Terraform config in `infra/`) starts, so the Phase 4 CloudFront
distribution is created fresh instead of being extended in place.

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
terraform plan     # review — should be ~10 resources
terraform apply
```

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
terraform apply     # re-uploads the S3 object (etag = filemd5)

# CloudFront caches for 24h by default. Invalidate to see the change now.
aws cloudfront create-invalidation \
  --distribution-id "$(terraform output -raw cloudfront_distribution_id)" \
  --paths '/index.html' '/'
```

## Teardown

```sh
terraform destroy
```

Everything the module created goes away, including the bucket contents
(`force_destroy = true`). CloudFront disable+delete takes 15-30 minutes;
Terraform handles both steps.

After `destroy` completes, the only Phase 0 residue should be in
`terraform.tfstate*` (local, gitignored). Delete those manually if you want
zero trace on disk.

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
