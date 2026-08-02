# VPC, subnets, and routing for the wedding site.
#
# Layout:
#
#   VPC 10.0.0.0/16 (DNS hostnames enabled so RDS gets a resolvable name)
#     ├── public subnet     10.0.1.0/24  us-east-1a   ──▶ IGW (Session 12 EC2 lives here)
#     ├── private subnet A  10.0.11.0/24 us-east-1a   ─── RDS primary
#     └── private subnet B  10.0.12.0/24 us-east-1b   ─── empty; RDS subnet-group filler
#
# Both private subnets attach to the same route table (local-only, no
# default route out). No NAT gateway — the private subnet doesn't need
# outbound internet, and NAT is ~$32/mo.
#
# aws_db_subnet_group in rds.tf requires ≥2 subnets in different AZs even
# for single-AZ instances; subnet B exists solely to satisfy that rule.

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_tag}-vpc"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_tag}-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  # EC2 gets a public IP by default when launched here (Session 12 also
  # attaches an Elastic IP, but this lets ad-hoc instances be reachable).
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_tag}-public-a"
    Tier = "public"
  }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "${var.project_tag}-private-a"
    Tier = "private"
  }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "us-east-1b"

  tags = {
    Name = "${var.project_tag}-private-b"
    Tier = "private"
    Note = "subnet-group-filler"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_tag}-public-rt"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  # No default route — the local route to 10.0.0.0/16 is implicit.

  tags = {
    Name = "${var.project_tag}-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}
