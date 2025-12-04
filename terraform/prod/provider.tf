provider "aws" {
  region = var.aws_region

  assume_role {
    role_arn = "arn:aws:iam::353130947195:role/Superschedules-Terraform"
  }
}
