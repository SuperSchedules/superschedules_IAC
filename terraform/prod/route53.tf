# Route53 configuration for eventzombie.com

# Reference existing hosted zone
data "aws_route53_zone" "eventzombie" {
  name         = "eventzombie.com"
  private_zone = false
}

# Apex domain - eventzombie.com → ALB
resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.eventzombie.zone_id
  name    = "eventzombie.com"
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

# www subdomain - www.eventzombie.com → ALB (Frontend SPA)
resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.eventzombie.zone_id
  name    = "www.eventzombie.com"
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

# api subdomain - api.eventzombie.com → ALB (Django API)
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.eventzombie.zone_id
  name    = "api.eventzombie.com"
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

# admin subdomain - admin.eventzombie.com → ALB (Django Admin)
resource "aws_route53_record" "admin" {
  zone_id = data.aws_route53_zone.eventzombie.zone_id
  name    = "admin.eventzombie.com"
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}
