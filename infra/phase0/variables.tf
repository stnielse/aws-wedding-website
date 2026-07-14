variable "domain_name" {
  type        = string
  description = "Apex domain, e.g. \"example.com\". The distribution serves both this and www.<domain_name>."
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN of the ACM certificate in us-east-1 covering both the apex and www.<domain_name>. Must already be Issued."
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for the apex domain. Alias records for apex and www are created inside this zone."
}

variable "project_tag" {
  type        = string
  description = "Value applied as the Project tag on all resources for cost attribution."
  default     = "wedding-site"
}
