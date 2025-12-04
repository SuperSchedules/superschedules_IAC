output "alb_dns_name" {
  description = "Public DNS name of the ALB"
  value       = aws_lb.app.dns_name
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint"
  value       = aws_db_instance.postgres.address
}

output "static_bucket" {
  description = "S3 static bucket name"
  value       = aws_s3_bucket.static.bucket
}

output "bluegreen_target_groups" {
  description = "Target group ARNs for the blue and green environments"
  value       = module.service_bluegreen.target_group_arns
}

output "bluegreen_autoscaling_groups" {
  description = "Auto Scaling Group names for blue and green"
  value       = module.service_bluegreen.autoscaling_group_names
}

output "bluegreen_active_color" {
  description = "Color currently receiving primary traffic"
  value       = module.service_bluegreen.active_color
}

output "active_color" {
  description = "Alias for bluegreen_active_color (used by Makefile)"
  value       = module.service_bluegreen.active_color
}

output "bluegreen_ready_to_flip" {
  description = "Indicates whether the standby color is healthy and ready for a flip"
  value       = module.service_bluegreen.ready_to_flip
}

output "bluegreen_readiness" {
  description = "Per-color readiness map"
  value       = module.service_bluegreen.readiness_by_color
}

output "ecr_repositories" {
  description = "ECR repository URIs for all services"
  value = {
    frontend  = aws_ecr_repository.frontend.repository_url
    api       = aws_ecr_repository.api.repository_url
    navigator = aws_ecr_repository.navigator.repository_url
    collector = aws_ecr_repository.collector.repository_url
  }
}
