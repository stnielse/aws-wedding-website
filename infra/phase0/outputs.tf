output "bucket_name" {
  value       = aws_s3_bucket.maintenance.bucket
  description = "S3 bucket holding the maintenance page."
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.maintenance.id
  description = "CloudFront distribution ID (useful for aws cloudfront create-invalidation)."
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.maintenance.domain_name
  description = "CloudFront-assigned domain, e.g. d1234.cloudfront.net. Route 53 aliases point here."
}
