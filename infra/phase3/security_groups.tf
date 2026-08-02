# Security groups for the app tier + DB tier.
#
#   ec2 SG ── ingress rules added by Session 12 (80/443 from anywhere,
#             SSM keeps 22 unnecessary — no SSH ingress planned)
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
  description = "EC2 app tier — ingress rules attached in Session 12."
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
# RDS security group
# --------------------------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${var.project_tag}-rds"
  description = "RDS Postgres — accepts 5432 from EC2 SG only."
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
