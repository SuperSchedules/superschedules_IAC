resource "random_password" "db" {
  length  = 24
  special = true
}

locals {
  db_password_effective = coalesce(var.db_password, random_password.db.result)
}

resource "aws_db_subnet_group" "db" {
  name       = "superschedules-prod-db-subnets"
  # RDS remains in existing private subnet (no cost impact, just grandfathered infrastructure)
  # Note: subnet-0a347f5a226038f4d still exists in AWS but removed from terraform state
  subnet_ids = ["subnet-0a347f5a226038f4d", "subnet-080be4b7478a56835"]

  tags = {
    Name = "superschedules-prod-db-subnets"
  }
}

resource "aws_db_instance" "postgres" {
  identifier              = "superschedules-prod-postgres"
  engine                  = "postgres"
  engine_version          = var.db_engine_version
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  max_allocated_storage   = 100
  db_name                 = var.db_name
  username                = var.db_username
  password                = local.db_password_effective
  db_subnet_group_name    = aws_db_subnet_group.db.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  multi_az                = false
  storage_encrypted       = true
  deletion_protection     = true
  skip_final_snapshot     = false
  publicly_accessible     = false

  tags = {
    Name = "superschedules-prod-postgres"
  }
}

