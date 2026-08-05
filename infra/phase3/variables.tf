variable "project_tag" {
  type        = string
  description = "Applied as the Project tag on every resource, and used as the base for bucket names + VPC/SG/DB identifiers."
  default     = "wedding-site"
}

variable "domain_name" {
  type        = string
  description = "Apex domain (same value used in phase 0's tfvars). Baked into ALLOWED_HOSTS + DOMAIN SSM params. Session 13's CloudFront also aliases apex + www."
}

variable "db_name" {
  type        = string
  description = "Initial database created inside the RDS Postgres instance. Django's DB_NAME env var points here."
  default     = "wedding"
}

variable "db_master_username" {
  type        = string
  description = "RDS master username. Not 'postgres' to reduce noise from generic scanners."
  default     = "wedding_admin"
}

variable "db_master_password" {
  type        = string
  description = "RDS master password. MUST be set in terraform.tfvars (gitignored). Minimum 8 chars per RDS, but pick something long."
  sensitive   = true
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN of the ACM certificate in us-east-1 covering apex + www (same cert phase 0 uses). Must already be Issued. Session 14 CloudFront viewer_certificate reads it."
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for the apex domain. Session 14 moves the apex + www alias records into phase 3 to point at this module's CloudFront distribution."
}
