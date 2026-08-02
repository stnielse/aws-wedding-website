# EC2 instance role S3 policy document — data-only this session, no role
# attachment yet (the role itself lands with EC2 in Session 12). Emitted
# as an output so Session 12's EC2 module can attach it via
# aws_iam_role_policy without redefining the shape here.
#
# Least-privilege per the critical rules: no wildcards on Resource, and
# the object-level actions are scoped to `${bucket}/*` while List is on
# the bucket root ARN itself. ListBucket cannot be scoped to a prefix via
# Resource (it's a bucket-level action); if we want prefix scoping later,
# it goes in a Condition (s3:prefix).

data "aws_iam_policy_document" "ec2_s3" {
  statement {
    sid    = "MediaBucketObjectRW"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.media.arn}/*"]
  }

  statement {
    sid       = "MediaBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.media.arn]
  }

  statement {
    sid    = "StaticBucketObjectRW"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.static.arn}/*"]
  }

  statement {
    sid       = "StaticBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.static.arn]
  }
}
