resource "aws_lb" "app" {
  name               = "superschedules-prod-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [for s in aws_subnet.public : s.id]

  tags = {
    Name = "superschedules-prod-alb"
  }
}

