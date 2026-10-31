variable "region" {
  type    = string
  default = "us-east-1"
}

variable "tfc_organization" {
  type    = string
  default = "successful-success"
}

variable "tfc_project" {
  type    = string
  default = "Default Project"
}

variable "tfc_workspace" {
  type    = string
  default = "successful-success"
}

data "tls_certificate" "tfc" {
  url = "https://app.terraform.io"
}

resource "aws_iam_openid_connect_provider" "tfc" {
  url             = "https://app.terraform.io"
  client_id_list  = ["aws.workload.identity"]
  thumbprint_list = [data.tls_certificate.tfc.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "tfc" {
  name = "hcp-terraform-${var.tfc_organization}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.tfc.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "app.terraform.io:aud" = "aws.workload.identity"
        }
        StringLike = {
          "app.terraform.io:sub" = "organization:${var.tfc_organization}:project:${var.tfc_project}:workspace:${var.tfc_workspace}:run_phase:*"
        }
      }
    }]
  })
}

# Course migration role: broad permissions are limited to this single HCP
# organization/project/workspace by the trust policy above.
resource "aws_iam_role_policy_attachment" "tfc" {
  role       = aws_iam_role.tfc.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

output "role_arn" {
  value       = aws_iam_role.tfc.arn
  description = "Role assumed by the successful-success HCP Terraform workspace"
}
