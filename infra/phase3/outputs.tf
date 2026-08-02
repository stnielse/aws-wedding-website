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
