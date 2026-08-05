resource "aws_cloudfront_origin_access_control" "maintenance" {
  name                              = "${var.project_tag}-phase0-oac"
  description                       = "OAC for the phase 0 maintenance bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "maintenance" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Phase 0 maintenance page for ${var.domain_name}"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  aliases = []

  origin {
    origin_id                = "s3-maintenance"
    domain_name              = aws_s3_bucket.maintenance.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.maintenance.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-maintenance"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS managed "CachingOptimized" cache policy — no cookies/headers/querystrings,
    # sensible TTLs for static content.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # Any 403 or 404 from S3 (missing key, denied key) is rewritten to the
  # maintenance page with a 200, so every path a visitor tries shows it.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
