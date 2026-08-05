# CloudFront distribution fronting the whole site. Three origins:
#
#   * s3-media  -> media bucket via OAC
#   * s3-static -> static bucket via OAC
#   * ec2-web   -> EC2 EIP over HTTP (nginx -> gunicorn -> Django)
#
# Three path-based behaviors on one distribution:
#
#   * /media/*  -> s3-media  (CachingOptimized, GET/HEAD only)
#   * /static/* -> s3-static (CachingOptimized, GET/HEAD only)
#   * default   -> ec2-web   (CachingDisabled, all methods, AllViewer)
#
# django-storages sets AWS_LOCATION='media' / 'static' in Session 14 so
# S3 keys carry the same prefixes as the CloudFront path patterns — no
# origin-side rewriting needed.
#
# AllViewer origin request policy on the EC2 behavior forwards the
# viewer's Host header so request.build_absolute_uri() produces links
# on the apex domain rather than ec2-<eip>.compute-1.amazonaws.com.
# ALLOWED_HOSTS already covers apex + www + EIP for direct debug hits.
#
# No custom_error_response — Django's own 404/500 pages should surface
# so real bugs stay visible. Phase 0's maintenance rewrite goes away
# with the phase 0 destroy.

# --------------------------------------------------------------------------
# Origin Access Controls — one per S3 origin.
# --------------------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "media" {
  name                              = "${var.project_tag}-media-oac"
  description                       = "OAC for the phase 3 media bucket."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "static" {
  name                              = "${var.project_tag}-static-oac"
  description                       = "OAC for the phase 3 static bucket."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --------------------------------------------------------------------------
# Distribution
# --------------------------------------------------------------------------

resource "aws_cloudfront_distribution" "web" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  comment         = "Phase 3 wedding site -- media + static + EC2 (${var.domain_name})"
  price_class     = "PriceClass_100" # US/Canada/Europe only; matches wedding-guest geography.

  aliases = [var.domain_name, "www.${var.domain_name}"]

  # --- Origins -----------------------------------------------------------

  origin {
    origin_id                = "s3-media"
    domain_name              = aws_s3_bucket.media.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.media.id
  }

  origin {
    origin_id                = "s3-static"
    domain_name              = aws_s3_bucket.static.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }

  origin {
    origin_id   = "ec2-web"
    domain_name = aws_eip.web.public_dns

    custom_origin_config {
      http_port                = 80
      https_port               = 443 # unused; EC2 does not serve HTTPS.
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 30
      origin_keepalive_timeout = 5
    }
  }

  # --- Default behavior: dynamic Django via EC2 --------------------------

  default_cache_behavior {
    target_origin_id       = "ec2-web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS-managed policies (IDs pinned so plan diffs stay stable):
    #   CachingDisabled — no cache; forward every request to origin.
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    #   AllViewer — forward Host, cookies, query strings, all viewer headers.
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  # --- /media/* -> S3 media bucket ---------------------------------------

  ordered_cache_behavior {
    path_pattern           = "/media/*"
    target_origin_id       = "s3-media"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # CachingOptimized — sensible TTLs, no cookies/headers/qs in cache key.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # --- /static/* -> S3 static bucket -------------------------------------

  ordered_cache_behavior {
    path_pattern           = "/static/*"
    target_origin_id       = "s3-static"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
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

  # Instance replace keeps the same EIP, so the ec2-web origin domain is
  # stable across replaces -- no distribution churn needed.
}