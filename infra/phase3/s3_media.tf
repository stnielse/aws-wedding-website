# S3 media bucket — Photo uploads and any admin-managed content that lives
# under MEDIA_URL. Versioned so accidental admin deletes don't lose wedding
# photos; a lifecycle rule expires non-current versions after 90 days to
# bound storage cost. NOT force_destroy so a stray `terraform destroy`
# can't nuke every photo in one command.

resource "aws_s3_bucket" "media" {
  bucket        = "${var.project_tag}-media-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.media]
}

# Bucket policy intentionally omitted this session — no CloudFront yet, so
# bucket access is limited to IAM principals in the account (the console
# user for verification, the EC2 role once Session 12 attaches it).
# Session 12 adds an aws_s3_bucket_policy with an AllowCloudFrontOACRead
# statement scoped to the real distribution ARN.
