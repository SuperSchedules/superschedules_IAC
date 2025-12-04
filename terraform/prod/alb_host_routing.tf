# Host-based routing rules for subdomain-specific traffic
# Preserves existing path-based routing + adds host-based routing
#
# Routing Strategy:
# - www.eventzombie.com / eventzombie.com → Frontend (nginx on port 80)
#   - EXCEPT /admin/*, /api/*, /chat/*, /static/* → Django (handled by existing path rules from blue/green module)
# - api.eventzombie.com → All traffic to Django API (port 8000)
# - admin.eventzombie.com → All traffic to Django Admin (port 8000)

# api.eventzombie.com → Django target group (ALL paths)
resource "aws_lb_listener_rule" "api_subdomain" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 5  # Higher priority than default rule (which is at 10)

  action {
    type             = "forward"
    target_group_arn = module.service_bluegreen.target_group_arns["${module.service_bluegreen.active_color}-django"]
  }

  condition {
    host_header {
      values = ["api.eventzombie.com"]
    }
  }

  tags = {
    Name = "api-subdomain-django"
  }
}

# admin.eventzombie.com → Django target group (ALL paths)
resource "aws_lb_listener_rule" "admin_subdomain" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 6  # Higher priority than default rule (which is at 10)

  action {
    type             = "forward"
    target_group_arn = module.service_bluegreen.target_group_arns["${module.service_bluegreen.active_color}-django"]
  }

  condition {
    host_header {
      values = ["admin.eventzombie.com"]
    }
  }

  tags = {
    Name = "admin-subdomain-django"
  }
}

# Note: www.eventzombie.com and eventzombie.com don't need explicit rules
# They will use the existing path-based routing from the blue/green module:
# - /admin/*, /api/*, /chat/*, /static/* → Django (priority 100)
# - Everything else → Frontend (priority 10)
