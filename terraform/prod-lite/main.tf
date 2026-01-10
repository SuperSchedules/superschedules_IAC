# Data sources for existing infrastructure

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

# Reference existing VPC from prod
data "aws_vpc" "prod" {
  filter {
    name   = "tag:Name"
    values = ["superschedules-prod-vpc"]
  }
}

# Reference existing public subnets from prod
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.prod.id]
  }
  filter {
    name   = "tag:Name"
    values = ["superschedules-prod-public-*"]
  }
}

# Reference existing RDS instance
data "aws_db_instance" "postgres" {
  db_instance_identifier = "superschedules-prod-postgres"
}

# Reference existing Route53 zone
data "aws_route53_zone" "main" {
  name         = var.domain_zone
  private_zone = false
}

# Reference existing RDS security group for allowing prod-lite access
data "aws_security_group" "db" {
  filter {
    name   = "tag:Name"
    values = ["superschedules-prod-db-sg"]
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "app" {
  name              = local.log_group
  retention_in_days = 7

  tags = {
    Name        = "${local.name_prefix}-logs"
    Environment = "prod-lite"
  }
}
