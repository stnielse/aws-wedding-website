# EC2 instance role. Three permission sets:
#   1. S3 access to media + static buckets (the Session 10 policy doc).
#   2. Read+decrypt on SSM params under /wedding-site/prod/*.
#   3. SSM Session Manager (via the AWS-managed AmazonSSMManagedInstanceCore
#      policy) — shell access without opening port 22.
#
# Least-privilege per the critical rules: SSM read is scoped to the exact
# parameter path prefix; S3 is scoped to the exact bucket ARNs.

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    sid     = "AllowEC2AssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project_tag}-ec2"
  description        = "EC2 instance role for the wedding-site web tier."
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

# --- S3 (bucket policy JSON from iam.tf) ---------------------------------
resource "aws_iam_role_policy" "ec2_s3" {
  name   = "s3-media-and-static"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_s3.json
}

# --- SSM parameter reads --------------------------------------------------
data "aws_iam_policy_document" "ec2_ssm_read" {
  statement {
    sid    = "ReadWeddingSiteParams"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = [
      "arn:aws:ssm:us-east-1:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*",
    ]
  }

  statement {
    sid       = "DecryptSecureStringParams"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"] # AWS-managed aws/ssm KMS key; ARN varies per region/account.

    # Scope to only aws/ssm (the default SecureString key) via a condition.
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.us-east-1.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "ec2_ssm_read" {
  name   = "ssm-read-wedding-site-prod"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_ssm_read.json
}

# --- Managed policy: AmazonSSMManagedInstanceCore ------------------------
resource "aws_iam_role_policy_attachment" "ec2_ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- Instance profile (what actually attaches to the EC2 instance) -------
resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_tag}-ec2"
  role = aws_iam_role.ec2.name
}
