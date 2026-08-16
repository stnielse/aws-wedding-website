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

  # Sweep orphaned multipart parts left behind by interrupted uploads
  # (e.g. SSO token expiry mid-`aws s3 sync` — Session 17 addendum).
  # Without this rule, aborted parts sit billed as storage indefinitely.
  # 3 days is well past the longest reasonable retry window for a
  # legitimate upload and cheap to trigger.
  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }

  depends_on = [aws_s3_bucket_versioning.media]
}

# Bucket policy: allow the phase 3 CloudFront distribution (via OAC) to
# GET objects. Scoped to the exact distribution ARN via AWS:SourceArn so
# no other distribution -- including phase 0's maintenance CF -- can read
# from this bucket. EC2 role still reads/writes via its own IAM policy
# (bucket policies and IAM policies grant additively).

data "aws_iam_policy_document" "media_bucket_policy" {
  statement {
    sid     = "AllowCloudFrontOACRead"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.media.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "media" {
  bucket = aws_s3_bucket.media.id
  policy = data.aws_iam_policy_document.media_bucket_policy.json

  depends_on = [aws_s3_bucket_public_access_block.media]
}
