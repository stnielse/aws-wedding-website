# GitHub Actions OIDC federation + deploy role (Session 15).
#
# The repo's Actions workflow assumes this role via short-lived OIDC
# tokens minted by GitHub -- no long-lived AWS access keys ever live
# in the repo or in GitHub secrets. Per project critical rule:
# "CI uses OIDC, EC2 uses an instance role" (CLAUDE.md).
#
# Trust policy is scoped by sub-claim to `repo:${github_repository}:
# ref:refs/heads/main` only -- pushes to other branches, PRs from
# forks, and tag pushes cannot assume the role. Aud claim is pinned
# to sts.amazonaws.com (the value aws-actions/configure-aws-
# credentials sends by default).
#
# The deploy role has narrow permissions:
#   1. s3:PutObject on the static bucket's deploy/ prefix only --
#      that's where CI uploads the built frontend tarball.
#   2. ssm:SendCommand scoped to the specific EC2 instance ARN and
#      the AWS-owned AWS-RunShellScript document. Nothing else can
#      be run, on no other target.
#   3. ssm:GetCommandInvocation on * -- required because the command
#      ID that scopes this action is only known after SendCommand
#      returns; there's no earlier ARN to condition on. Scoped by
#      InstanceId in the condition block.

# --------------------------------------------------------------------------
# OIDC provider
#
# Thumbprints are for GitHub's OIDC issuer intermediate cert. AWS
# validates the issuer's TLS chain natively for the well-known
# GitHub issuer, so the thumbprints are effectively vestigial, but
# the AWS provider still requires the argument. Two published values
# are included to cover cert rotation without a terraform apply.
# --------------------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]

  tags = {
    Name = "${var.project_tag}-github-oidc"
  }
}

# --------------------------------------------------------------------------
# Deploy role: trust policy
# --------------------------------------------------------------------------

data "aws_iam_policy_document" "github_deploy_trust" {
  statement {
    sid     = "AllowGitHubOIDCFromMain"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.project_tag}-github-deploy"
  description        = "Assumed by GitHub Actions (main branch only) to upload frontend build artifacts and trigger SSM RunCommand deploys."
  assume_role_policy = data.aws_iam_policy_document.github_deploy_trust.json

  # Cap how long a single workflow-issued session can last. Deploy
  # itself is measured in single-digit minutes; 1 hour is a generous
  # ceiling and matches AWS's default session duration.
  max_session_duration = 3600
}

# --------------------------------------------------------------------------
# Deploy role: inline policy
# --------------------------------------------------------------------------

data "aws_iam_policy_document" "github_deploy" {
  # (1) Upload frontend build tarball to the static bucket's deploy/
  # prefix. Scoped to the prefix -- CI cannot overwrite hashed
  # collectstatic output or any other object.
  statement {
    sid    = "PutFrontendArtifact"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
    ]
    resources = ["${aws_s3_bucket.static.arn}/deploy/*"]
  }

  # (2) SSM SendCommand -- only the AWS-owned RunShellScript document,
  # only against the wedding-site EC2 instance.
  statement {
    sid     = "SendDeployCommand"
    effect  = "Allow"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ssm:us-east-1::document/AWS-RunShellScript",
      aws_instance.web.arn,
    ]
  }

  # (3) Poll the invocation for completion. Can't scope by command ID
  # (CI only learns the ID after SendCommand returns) and command-
  # invocation resources don't carry tags that ssm:resourceTag/* can
  # match on, so this stays at "*". The role is only assumable from
  # main of this repo (see trust policy above), so worst-case
  # exposure is a compromised main branch reading historical
  # SendCommand output -- no write path.
  statement {
    sid    = "PollDeployCommand"
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
