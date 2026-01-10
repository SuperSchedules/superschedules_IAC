terraform {
  backend "s3" {
    bucket       = "superschedules-tf-state"
    key          = "prod-lite/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
