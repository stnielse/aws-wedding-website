# S3 static bucket — collectstatic output (hashed by ManifestFilesMixin).
# Not versioned — every deploy regenerates the tree, and old hashed files
# are safe to lose after CDN caches expire. force_destroy = true so it's
# cheap to blow away and recreate during Phase 3 iteration.

resource "aws_s3_bucket" "static" {
  bucket        = "${var.project_tag}-static-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_ownership_controls" "static" {
  bucket = aws_s3_bucket.static.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "static" {
  bucket = aws_s3_bucket.static.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket policy: identical shape to media's -- grants GetObject to the
# phase 3 CloudFront distribution's OAC principal only. See s3_media.tf
# for rationale on the SourceArn scoping.

data "aws_iam_policy_document" "static_bucket_policy" {
  statement {
    sid     = "AllowCloudFrontOACRead"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.static.arn}/*"]

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

resource "aws_s3_bucket_policy" "static" {
  bucket = aws_s3_bucket.static.id
  policy = data.aws_iam_policy_document.static_bucket_policy.json

  depends_on = [aws_s3_bucket_public_access_block.static]
}
