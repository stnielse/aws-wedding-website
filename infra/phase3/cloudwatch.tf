# CloudWatch log aggregation for the web tier.
#
# Three log groups, all 30-day retention (project rule: every log
# group carries an explicit retention_in_days; without it, groups
# default to "Never expire" and quietly rack up bytes):
#
#   /wedding-site/django          -- gunicorn stderr from journald.
#                                    Django logs land here as JSON
#                                    records (config.log_formatters.
#                                    JsonFormatter). Access logs from
#                                    gunicorn are plain text on the
#                                    same stream and are ignored by
#                                    the JSON metric filter below.
#   /wedding-site/nginx-access    -- /var/log/nginx/access.log
#   /wedding-site/nginx-error     -- /var/log/nginx/error.log
#
# The CloudWatch Agent on the instance (installed via user_data) is
# what actually ships records into these groups. Its config lives in
# SSM (see ssm.tf: CLOUDWATCH_AGENT_CONFIG) so tweaking what gets
# shipped is a terraform apply + one SSM SendCommand, not an
# instance replace.
#
# One metric filter + alarm on the Django group: any JSON record
# with .level == ERROR or CRITICAL trips a page to the ops email
# via SNS. Threshold is 1 (not "many") because at anticipated
# traffic (~a few hundred hits/day peak, ~50 guests) steady-state
# ERROR rate should be zero -- false positives are cheap, missed
# real errors are what we're avoiding.

# --------------------------------------------------------------------------
# Log groups
# --------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "django" {
  name              = "/wedding-site/django"
  retention_in_days = 30

  tags = {
    Name = "${var.project_tag}-django-logs"
  }
}

resource "aws_cloudwatch_log_group" "nginx_access" {
  name              = "/wedding-site/nginx-access"
  retention_in_days = 30

  tags = {
    Name = "${var.project_tag}-nginx-access-logs"
  }
}

resource "aws_cloudwatch_log_group" "nginx_error" {
  name              = "/wedding-site/nginx-error"
  retention_in_days = 30

  tags = {
    Name = "${var.project_tag}-nginx-error-logs"
  }
}

# --------------------------------------------------------------------------
# SNS topic + email subscription for the ERROR alarm.
#
# Email subscriptions require the recipient to click a confirmation
# link in their inbox. Terraform's plan will show pending_confirmation
# for the subscription until then; that's expected and non-fatal --
# the topic still exists, but nothing is delivered.
# --------------------------------------------------------------------------

resource "aws_sns_topic" "django_errors" {
  name = "${var.project_tag}-django-errors"

  tags = {
    Name = "${var.project_tag}-django-errors"
  }
}

resource "aws_sns_topic_subscription" "django_errors_email" {
  topic_arn = aws_sns_topic.django_errors.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# --------------------------------------------------------------------------
# Metric filter -> alarm.
#
# The filter pattern uses CloudWatch's JSON syntax: only lines that
# parse as JSON and have a top-level "level" field matching ERROR or
# CRITICAL contribute to the metric. Non-JSON lines (like gunicorn's
# plain-text access logs sharing this stream) are silently skipped.
# --------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "django_errors" {
  name           = "${var.project_tag}-django-errors"
  log_group_name = aws_cloudwatch_log_group.django.name
  pattern        = "{ ($.level = \"ERROR\") || ($.level = \"CRITICAL\") }"

  metric_transformation {
    name          = "DjangoErrorCount"
    namespace     = "WeddingSite/App"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "django_errors" {
  alarm_name        = "${var.project_tag}-django-errors"
  alarm_description = "Django logged an ERROR or CRITICAL record in the last 5 minutes."

  namespace           = "WeddingSite/App"
  metric_name         = "DjangoErrorCount"
  statistic           = "Sum"
  period              = 300 # 5 minutes
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.django_errors.arn]
  ok_actions    = [aws_sns_topic.django_errors.arn]

  tags = {
    Name = "${var.project_tag}-django-errors"
  }
}
