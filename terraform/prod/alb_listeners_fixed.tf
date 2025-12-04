# HTTPS Listener (port 443) - Primary listener for application traffic
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.app.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"  # Modern TLS 1.3 policy
  certificate_arn   = local.eventzombie_certificate_arn

  # Default action - will be overridden by listener rules
  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "text/plain"
      message_body = "Service Unavailable"
      status_code  = "503"
    }
  }

  tags = {
    Name = "superschedules-prod-https"
  }
}

# HTTP Listener (port 80) - Redirect to HTTPS
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = {
    Name = "superschedules-prod-http-redirect"
  }
}
