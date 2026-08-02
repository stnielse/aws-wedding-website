variable "project_tag" {
  type        = string
  description = "Applied as the Project tag on every resource, and used as the base for bucket names (see s3_media.tf / s3_static.tf)."
  default     = "wedding-site"
}
