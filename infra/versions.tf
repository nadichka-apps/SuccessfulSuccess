terraform {
  required_version = ">= 1.10"

  cloud {
    organization = "successful-success"

    workspaces {
      name = "successful-success"
    }
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}
