# Security Group for prod-lite instance

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-sg"
  description = "Prod-lite instance security group - HTTP, HTTPS, SSH"
  vpc_id      = data.aws_vpc.prod.id

  # HTTP (for Let's Encrypt ACME challenge and redirect to HTTPS)
  ingress {
    description      = "HTTP from anywhere"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  # HTTPS
  ingress {
    description      = "HTTPS from anywhere"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  # SSH (optional - only if ssh_allowed_cidrs is set)
  # Not needed if using SSM Session Manager (recommended)
  dynamic "ingress" {
    for_each = length(var.ssh_allowed_cidrs) > 0 ? [1] : []
    content {
      description = "SSH from allowed IPs (optional - prefer SSM)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.ssh_allowed_cidrs
    }
  }

  # All outbound traffic
  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name        = "${local.name_prefix}-sg"
    Environment = "prod-lite"
  }
}

# Allow prod-lite to access the shared RDS database
resource "aws_security_group_rule" "db_from_prod_lite" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = data.aws_security_group.db.id
  source_security_group_id = aws_security_group.app.id
  description              = "PostgreSQL from prod-lite"
}
