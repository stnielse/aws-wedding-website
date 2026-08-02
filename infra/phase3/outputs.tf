# --------------------------------------------------------------------------
# S3 (Session 10)
# --------------------------------------------------------------------------

output "media_bucket_name" {
  value       = aws_s3_bucket.media.bucket
  description = "S3 bucket for MEDIA_URL uploads (django-storages default backend)."
}

output "media_bucket_arn" {
  value       = aws_s3_bucket.media.arn
  description = "ARN of the media bucket (consumed by Session 12's CloudFront + EC2 role)."
}

output "media_bucket_regional_domain_name" {
  value       = aws_s3_bucket.media.bucket_regional_domain_name
  description = "Regional S3 domain (e.g. bucket.s3.us-east-1.amazonaws.com). Session 12 wires this as a CloudFront origin."
}

output "static_bucket_name" {
  value       = aws_s3_bucket.static.bucket
  description = "S3 bucket for collectstatic output (ManifestS3StaticStorage backend)."
}

output "static_bucket_arn" {
  value       = aws_s3_bucket.static.arn
  description = "ARN of the static bucket."
}

output "static_bucket_regional_domain_name" {
  value       = aws_s3_bucket.static.bucket_regional_domain_name
  description = "Regional S3 domain for the static bucket. Session 12 CloudFront origin."
}

output "ec2_s3_policy_json" {
  value       = data.aws_iam_policy_document.ec2_s3.json
  description = "JSON policy doc granting the EC2 instance role S3 access to both buckets. Session 12 attaches it via aws_iam_role_policy."
}

# --------------------------------------------------------------------------
# Network (Session 11)
# --------------------------------------------------------------------------

output "vpc_id" {
  value       = aws_vpc.main.id
  description = "VPC ID (Session 12 EC2 attaches here)."
}

output "public_subnet_id" {
  value       = aws_subnet.public.id
  description = "Public subnet for EC2 (Session 12)."
}

output "private_subnet_ids" {
  value       = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  description = "Private subnet IDs (RDS subnet group and any future private-tier resources)."
}

output "ec2_security_group_id" {
  value       = aws_security_group.ec2.id
  description = "EC2 SG ID — Session 12 attaches ingress rules for 80/443 and (optionally) 22."
}

output "rds_security_group_id" {
  value       = aws_security_group.rds.id
  description = "RDS SG ID (already wired to accept 5432 from the EC2 SG)."
}

# --------------------------------------------------------------------------
# RDS (Session 11)
# --------------------------------------------------------------------------

output "db_endpoint" {
  value       = aws_db_instance.wedding.endpoint
  description = "RDS endpoint in host:port form (e.g. wedding-site-postgres.abc.us-east-1.rds.amazonaws.com:5432). Feed into Django's DB_HOST + DB_PORT env vars."
}

output "db_address" {
  value       = aws_db_instance.wedding.address
  description = "RDS hostname only, no port. Use for DB_HOST."
}

output "db_port" {
  value       = aws_db_instance.wedding.port
  description = "RDS port (always 5432 for this config)."
}

output "db_name" {
  value       = aws_db_instance.wedding.db_name
  description = "Initial database name inside the RDS instance."
}

output "db_master_username" {
  value       = aws_db_instance.wedding.username
  description = "RDS master username (for Django's DB_USER env var)."
}

output "rds_log_group_name" {
  value       = aws_cloudwatch_log_group.rds_postgresql.name
  description = "CloudWatch log group receiving RDS's postgresql log stream."
}
