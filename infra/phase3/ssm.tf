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
  description = "Comma-separated ALLOWED_HOSTS. CloudFront AllViewer forwards viewer Host verbatim, so apex + www cover CloudFront-served requests. EIP retained for direct-hit debugging."
  type        = "String"
  value       = join(",", [aws_eip.web.public_ip, var.domain_name, "www.${var.domain_name}"])
}

resource "aws_ssm_parameter" "csrf_trusted_origins" {
  name        = "${local.ssm_prefix}/CSRF_TRUSTED_ORIGINS"
  description = "Comma-separated Django CSRF_TRUSTED_ORIGINS. Same shape as ALLOWED_HOSTS but each entry is a scheme://host origin."
  type        = "String"
  value       = join(",", ["https://${var.domain_name}", "https://www.${var.domain_name}"])
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

# Both media and static are served through the same CloudFront distribution
# on the apex domain -- /media/* and /static/* cache behaviors route to the
# right S3 origin. django-storages builds URLs like
# https://<domain>/media/<key> and https://<domain>/static/<key> (with
# AWS_LOCATION='media' / 'static' on the storage options).

resource "aws_ssm_parameter" "aws_s3_custom_domain" {
  name        = "${local.ssm_prefix}/AWS_S3_CUSTOM_DOMAIN"
  description = "Public host django-storages puts in media URLs. Apex domain (routed through CloudFront /media/*)."
  type        = "String"
  value       = var.domain_name
}

resource "aws_ssm_parameter" "aws_static_custom_domain" {
  name        = "${local.ssm_prefix}/AWS_STATIC_CUSTOM_DOMAIN"
  description = "Public host django-storages puts in static URLs. Apex domain (routed through CloudFront /static/*)."
  type        = "String"
  value       = var.domain_name
}

# --------------------------------------------------------------------------
# CloudWatch Agent config (Session 15).
#
# Stored in SSM so tweaking what the agent tails is a terraform apply +
# one SSM SendCommand ("amazon-cloudwatch-agent-ctl -a fetch-config -s")
# on the box -- no instance replace needed. The agent's fetch-config
# subcommand knows the ssm: URI scheme natively.
#
# All three streams come from files -- amazon-cloudwatch-agent 1.300
# does not accept `journald` under logs.logs_collected (only files,
# windows_events, emf), so gunicorn.service was switched from
# StandardOutput=journal to append:/var/log/gunicorn/gunicorn.log in
# gunicorn.service.tftpl. The agent tails that file, which carries
# the same JsonFormatter output the Django ERROR/CRITICAL metric
# filter (cloudwatch.tf) matches on.
# --------------------------------------------------------------------------

resource "aws_ssm_parameter" "cloudwatch_agent_config" {
  name        = "${local.ssm_prefix}/CLOUDWATCH_AGENT_CONFIG"
  description = "JSON config for amazon-cloudwatch-agent on the EC2 web tier. Fetched with 'amazon-cloudwatch-agent-ctl -a fetch-config -s -c ssm:<this-param-name>'."
  type        = "String"
  tier        = "Standard"

  value = jsonencode({
    agent = {
      run_as_user = "root"
    }
    logs = {
      logs_collected = {
        files = {
          collect_list = [
            {
              file_path         = "/var/log/nginx/access.log"
              log_group_name    = aws_cloudwatch_log_group.nginx_access.name
              log_stream_name   = "{instance_id}"
              retention_in_days = 30
              timezone          = "UTC"
            },
            {
              file_path         = "/var/log/nginx/error.log"
              log_group_name    = aws_cloudwatch_log_group.nginx_error.name
              log_stream_name   = "{instance_id}"
              retention_in_days = 30
              timezone          = "UTC"
            },
            {
              file_path         = "/var/log/gunicorn/gunicorn.log"
              log_group_name    = aws_cloudwatch_log_group.django.name
              log_stream_name   = "{instance_id}"
              retention_in_days = 30
              timezone          = "UTC"
            },
          ]
        }
      }
    }
  })
}
