variable "project_name" {
  type        = string
  description = "Stable prefix used by this deployment"
}

variable "region" {
  type        = string
  description = "AWS region for the migrated resources"
}

variable "app_urls" {
  type        = list(string)
  description = "Cognito callback and logout URLs"
}

variable "google_client_id" {
  type        = string
  description = "Google OAuth web client ID"
}

variable "google_client_secret" {
  type        = string
  sensitive   = true
  description = "Google OAuth web client secret; set as a sensitive HCP variable"
}

variable "database_url" {
  type        = string
  sensitive   = true
  description = "Report Builder connection URL; set as a sensitive HCP variable"
}

variable "reports_image_uri" {
  type        = string
  description = "Digest-pinned Lambda image used by the reports stack"
}

variable "parser_image_uri" {
  type        = string
  description = "Digest-pinned Lambda image used by the agenda parser"
}

variable "vpc_id" {
  type        = string
  description = "VPC containing Aurora and the Report Builder"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnets used by the Report Builder Lambda"
}

variable "function_security_group_id" {
  type        = string
  description = "Security group attached to the Report Builder Lambda"
}

variable "route_table_ids" {
  type        = list(string)
  description = "Route tables attached to the S3 gateway endpoint"
}

variable "app_timezone" {
  type        = string
  description = "Timezone used by report generation"
}

variable "log_level" {
  type        = string
  description = "Application log level for report Lambdas"
}

variable "sender_email" {
  type        = string
  description = "Verified SES sender address for weekly reports"
  sensitive   = true
}

variable "recipient_email" {
  type        = string
  description = "Recipient address for weekly reports"
  sensitive   = true
}

variable "parser_model" {
  type        = string
  description = "Bedrock model used by the agenda parser"
}

variable "allowed_origin" {
  type        = string
  description = "Browser origin allowed to call the agenda parser"
}
