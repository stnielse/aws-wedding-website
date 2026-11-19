# Security groups for the app tier + DB tier.
#
#   ec2 SG ── ingress 80 from the CloudFront origin-facing prefix list
#             only (Session 21; was 80/443 from anywhere in Session 12).
#             SSM keeps 22 unnecessary — no SSH ingress planned.
#   rds SG ── ingress 5432 from ec2 SG only (reference-by-SG, not CIDR)
#
# Egress rules declared explicitly. Terraform's aws_security_group used
# to include a default "allow all egress" rule, but AWS strips it on
# creation unless we declare it via aws_vpc_security_group_egress_rule.
#
# The rule split (SG resource + separate rule resources) is the newer
# AWS-provider pattern — it lets Session 12 append EC2 ingress rules
# without touching the SG's own resource, avoiding drift.

# --------------------------------------------------------------------------
# EC2 security group
# --------------------------------------------------------------------------
resource "aws_security_group" "ec2" {
  name        = "${var.project_tag}-ec2"
  description = "EC2 app tier - ingress rules attached in Session 12."
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_tag}-ec2-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "ec2_all_out" {
  security_group_id = aws_security_group.ec2.id
  description       = "EC2 needs outbound for OS updates, S3, RDS, CloudWatch."
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# --------------------------------------------------------------------------
# EC2 ingress (Session 12, locked down in Session 21) — port 80 from the
# CloudFront origin-facing ranges only. No SSH; SSM Session Manager
# covers shell access without opening port 22.
#
# Session 21 replaced the original 0.0.0.0/0 rule after the NGINX2ROOT
# disclosure (five nginx RCE CVEs, 2026-11-18). We were not vulnerable to
# any of the five, but the audit made the point that the S20 nginx
# `return 444` catchall is not a mitigation for parser-level memory bugs:
# protocol parsing happens before server_name selection, so nginx never
# reaches the 444 decision. Keeping the internet off port 80 is the
# control that actually helps for the next one.
#
# The port-443 rule from Session 12 was deleted rather than converted —
# nothing listens on 443 (nginx declares only `listen 80`) and CloudFront
# dials plaintext because origin_protocol_policy = "http-only", so it was
# a dead rule. Deleting it also keeps us inside the rules quota; see the
# weight note on the data source below.
# --------------------------------------------------------------------------

# AWS creates and maintains this list; a rule referencing it picks up
# CloudFront IP-range changes automatically, with no Lambda and no
# scheduled refresh. (Session 20 deferred this lockdown believing a
# refresh job was required — that applies to the legacy
# ip-ranges.json-parsing pattern, not to the AWS-managed list.)
#
# Resolved by name, not by a hardcoded pl-* id: the id differs per
# region. The IPv6 companion list
# (com.amazonaws.global.ipv6.cloudfront.origin-facing) is deliberately
# not referenced — this SG has no IPv6 ingress, so IPv6 is already
# closed by default-deny, and a second list would double the quota
# weight to buy access nothing needs.
data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# Quota note: a prefix-list reference consumes the list's *published
# weight* against the "inbound rules per security group" quota
# (L-0EA8095F, default 60), not its current entry count. This list
# weighs 55, putting this SG at 55/60 inbound. Any future inbound rule
# has 5 slots; past that, raise the quota rather than reverting to CIDR.
resource "aws_vpc_security_group_ingress_rule" "ec2_http" {
  security_group_id = aws_security_group.ec2.id
  description       = "HTTP from CloudFront origin-facing ranges only (Session 21 lockdown)."
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id
}

# --------------------------------------------------------------------------
# RDS security group
# --------------------------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${var.project_tag}-rds"
  description = "RDS Postgres - accepts 5432 from EC2 SG only."
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${var.project_tag}-rds-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ec2" {
  security_group_id            = aws_security_group.rds.id
  description                  = "Postgres from the app tier."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.ec2.id
}

resource "aws_vpc_security_group_egress_rule" "rds_all_out" {
  security_group_id = aws_security_group.rds.id
  description       = "RDS internal maintenance traffic."
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
