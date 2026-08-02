# RDS Postgres 17.10 on db.t3.micro. Private subnets only; SG restricts
# 5432 to the EC2 SG. CloudWatch log export for the ``postgresql`` log
# stream; the log group is pre-created with 30-day retention per the
# handoff amendment (RDS would otherwise create it with unbounded
# retention on first write).

resource "aws_db_subnet_group" "private" {
  name        = "${var.project_tag}-private"
  description = "RDS private subnets (needs ≥2 AZs even for single-AZ)."
  subnet_ids  = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = {
    Name = "${var.project_tag}-db-subnet-group"
  }
}

# Pre-create the log group so retention is set before RDS writes to it.
# The group name is fixed by RDS — must be exactly
# /aws/rds/instance/${db_id}/postgresql — so we construct it from the
# same identifier the DB uses.
locals {
  db_identifier = "${var.project_tag}-postgres"
}

resource "aws_cloudwatch_log_group" "rds_postgresql" {
  name              = "/aws/rds/instance/${local.db_identifier}/postgresql"
  retention_in_days = 30

  tags = {
    Name = "${var.project_tag}-rds-postgresql-logs"
  }
}

resource "aws_db_instance" "wedding" {
  identifier = local.db_identifier

  engine         = "postgres"
  engine_version = "17.10"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 20 # No autoscaling — keep the bill deterministic.
  storage_type          = "gp3"
  storage_encrypted     = true
  # Uses the AWS-managed aws/rds KMS key when kms_key_id is null.

  db_name  = var.db_name
  username = var.db_master_username
  password = var.db_master_password

  db_subnet_group_name   = aws_db_subnet_group.private.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  port                   = 5432

  multi_az            = false
  deletion_protection = false # Flip pre-wedding if we want an extra safety net.

  backup_retention_period  = 7
  backup_window            = "07:00-09:00" # UTC → early morning US
  delete_automated_backups = true
  copy_tags_to_snapshot    = true
  skip_final_snapshot      = true

  maintenance_window         = "sun:09:00-sun:11:00"
  auto_minor_version_upgrade = true

  performance_insights_enabled    = false
  monitoring_interval             = 0 # Enhanced monitoring off — extra cost.
  enabled_cloudwatch_logs_exports = ["postgresql"]

  apply_immediately = false

  # Make sure the log group exists before RDS tries to write into it,
  # otherwise RDS auto-creates it with default (never-expire) retention
  # and we can't take it over.
  depends_on = [aws_cloudwatch_log_group.rds_postgresql]

  tags = {
    Name = "${var.project_tag}-postgres"
  }
}
