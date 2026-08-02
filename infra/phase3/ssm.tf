# SSM Parameter Store — one source of truth for every env var Django needs
# in production. SecureString for secrets (KMS-encrypted at rest with the
# AWS-managed aws/ssm key), plain String for the rest.
#
# All params live under /wedding-site/prod/. user_data fetches everything
# with a single get-parameters-by-path --with-decryption --recursive call,
# formats to KEY=value lines, writes to backend/.env, then starts gunicorn
# which loads via systemd EnvironmentFile.
#
# Rotation of any value: aws ssm put-parameter --overwrite + systemctl
# restart gunicorn. No Terraform state churn required for rotation of a
# secret handled outside Terraform (though we do generate DJANGO_SECRET_KEY
# via random_password inside Terraform for convenience).

locals {
  ssm_prefix = "/wedding-site/prod"
}

# --------------------------------------------------------------------------
# Secrets (SecureString)
# --------------------------------------------------------------------------

resource "random_password" "django_secret_key" {
  length           = 50
  special          = true
  override_special = "!@#$%*-_=+"
}

resource "aws_ssm_parameter" "django_secret_key" {
  name        = "${local.ssm_prefix}/DJANGO_SECRET_KEY"
  description = "Django SECRET_KEY. Rotate via terraform apply -replace on random_password.django_secret_key."
  type        = "SecureString"
  value       = random_password.django_secret_key.result
  tier        = "Standard"
}

resource "aws_ssm_parameter" "db_password" {
  name        = "${local.ssm_prefix}/DB_PASSWORD"
  description = "RDS Postgres master password. Same value as var.db_master_password."
  type        = "SecureString"
  value       = var.db_master_password
  tier        = "Standard"
}

# --------------------------------------------------------------------------
# Non-secrets (String) — grouped one per resource so future adds/removes
# leave a clean plan diff.
# --------------------------------------------------------------------------

resource "aws_ssm_parameter" "db_host" {
  name  = "${local.ssm_prefix}/DB_HOST"
  type  = "String"
  value = aws_db_instance.wedding.address
}

resource "aws_ssm_parameter" "db_port" {
  name  = "${local.ssm_prefix}/DB_PORT"
  type  = "String"
  value = tostring(aws_db_instance.wedding.port)
}

resource "aws_ssm_parameter" "db_name" {
  name  = "${local.ssm_prefix}/DB_NAME"
  type  = "String"
  value = aws_db_instance.wedding.db_name
}

resource "aws_ssm_parameter" "db_user" {
  name  = "${local.ssm_prefix}/DB_USER"
  type  = "String"
  value = aws_db_instance.wedding.username
}

resource "aws_ssm_parameter" "domain" {
  name        = "${local.ssm_prefix}/DOMAIN"
  description = "Public domain (used by ALLOWED_HOSTS and Django url reversing)."
  type        = "String"
  value       = var.domain_name
}

resource "aws_ssm_parameter" "allowed_hosts" {
  name        = "${local.ssm_prefix}/ALLOWED_HOSTS"
  description = "Comma-separated ALLOWED_HOSTS. Session 12: EIP + domain. Session 13 drops EIP once CloudFront is fronting."
  type        = "String"
  value       = join(",", [aws_eip.web.public_ip, var.domain_name, "www.${var.domain_name}"])
}

resource "aws_ssm_parameter" "aws_region" {
  name  = "${local.ssm_prefix}/AWS_REGION"
  type  = "String"
  value = "us-east-1"
}

resource "aws_ssm_parameter" "aws_storage_bucket_name" {
  name  = "${local.ssm_prefix}/AWS_STORAGE_BUCKET_NAME"
  type  = "String"
  value = aws_s3_bucket.media.bucket
}

resource "aws_ssm_parameter" "aws_static_bucket_name" {
  name  = "${local.ssm_prefix}/AWS_STATIC_BUCKET_NAME"
  type  = "String"
  value = aws_s3_bucket.static.bucket
}
