# Route 53 apex + www alias records for the site.
#
# These records existed under phase 0 (pointing at the maintenance
# distribution). Session 14 migrates them into phase 3 so the module that
# owns the target distribution also owns the DNS records pointing at it.
#
# Migration flow (one-time, executed as part of Session 14 apply):
#
#   1. `terraform -chdir=infra/phase0 state rm 'aws_route53_record.apex_a'`
#      (and apex_aaaa, www_a, www_aaaa). Records stay in AWS -- state rm
#      only detaches them from Terraform.
#   2. `terraform -chdir=infra/phase3 apply` -- the `import` blocks below
#      attach the existing records to phase 3 state; on the same apply,
#      the alias target flips from phase 0's CloudFront to phase 3's.
#      Route 53 alias swaps are near-instant (no TTL wait).
#   3. `terraform -chdir=infra/phase0 destroy` -- records are no longer in
#      phase 0 state, so destroy leaves them alone. Phase 0 CloudFront +
#      S3 + OAC go away (CloudFront disable+delete takes 15-30 min).
#
# The import block IDs use Route 53's `ZONEID_NAME_TYPE` shape.

resource "aws_route53_record" "apex_a" {
  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex_aaaa" {
  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_a" {
  zone_id = var.hosted_zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_aaaa" {
  zone_id = var.hosted_zone_id
  name    = "www.${var.domain_name}"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

# --------------------------------------------------------------------------
# Import blocks -- one-shot state attaches. Remove after Session 14 apply
# has landed (they're no-ops on subsequent runs but noisy in plan output).
# --------------------------------------------------------------------------

import {
  to = aws_route53_record.apex_a
  id = "${var.hosted_zone_id}_${var.domain_name}_A"
}

import {
  to = aws_route53_record.apex_aaaa
  id = "${var.hosted_zone_id}_${var.domain_name}_AAAA"
}

import {
  to = aws_route53_record.www_a
  id = "${var.hosted_zone_id}_www.${var.domain_name}_A"
}

import {
  to = aws_route53_record.www_aaaa
  id = "${var.hosted_zone_id}_www.${var.domain_name}_AAAA"
}