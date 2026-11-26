variable "project_id" {
  type        = string
  description = "Globally unique GCP project ID (create the project before applying)."
}

variable "region" {
  type        = string
  description = "Region for Cloud Run, Cloud SQL and Artifact Registry."
  default     = "us-central1"
}

variable "project_name" {
  type        = string
  description = "Resource name prefix."
  default     = "successfulsuccess"
}

variable "api_image" {
  type        = string
  description = "Container image deployed to Cloud Run and the migration job."
  # A public bootstrap image lets the first apply create Artifact Registry and
  # Cloud Run. Replace it with the pushed project image before serving traffic.
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "cognito_region" {
  type        = string
  description = "AWS region of the existing Cognito user pool."
  default     = "us-east-1"
}

variable "cognito_user_pool_id" {
  type        = string
  description = "Existing AWS Cognito user pool ID."
}

variable "cognito_client_id" {
  type        = string
  description = "Existing AWS Cognito app client ID."
}

variable "app_timezone" {
  type        = string
  description = "Timezone used by the API."
  default     = "Europe/Kyiv"
}

variable "db_password_length" {
  type        = number
  description = "Length of the generated PostgreSQL password."
  default     = 32
}
