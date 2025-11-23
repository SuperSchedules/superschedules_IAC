terraform {
  backend "s3" {
    bucket         = "superschedules-tf-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    # Use S3-native lockfile (Terraform >=1.9). DynamoDB table no longer required.
    use_lockfile   = true
  }
}
