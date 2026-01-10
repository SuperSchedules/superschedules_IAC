# Outputs for prod-lite environment

output "asg_name" {
  description = "Auto Scaling Group name"
  value       = aws_autoscaling_group.app.name
}

output "launch_template_id" {
  description = "Launch template ID"
  value       = aws_launch_template.app.id
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.app.id
}

output "instance_profile_name" {
  description = "Instance profile name"
  value       = aws_iam_instance_profile.ec2.name
}

output "domains" {
  description = "All domains configured for this instance"
  value       = local.all_domains
}

output "api_url" {
  description = "API URL"
  value       = "https://${var.api_domain}"
}

output "www_url" {
  description = "Frontend URL"
  value       = "https://${var.www_domain}"
}

output "admin_url" {
  description = "Admin URL"
  value       = "https://${var.admin_domain}"
}

output "dns_lambda_arn" {
  description = "DNS updater Lambda ARN"
  value       = aws_lambda_function.dns_updater.arn
}

output "log_group" {
  description = "CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.app.name
}

output "db_host" {
  description = "Database host (shared with prod)"
  value       = data.aws_db_instance.postgres.address
}

output "vpc_id" {
  description = "VPC ID (shared with prod)"
  value       = data.aws_vpc.prod.id
}

output "ssm_connect_command" {
  description = "AWS CLI command to connect via SSM Session Manager"
  value       = "aws ssm start-session --target <INSTANCE_ID> --region ${var.aws_region}"
}

output "get_instance_id_command" {
  description = "AWS CLI command to get the instance ID"
  value       = "aws ec2 describe-instances --region ${var.aws_region} --filters \"Name=tag:Name,Values=${local.name_prefix}\" \"Name=instance-state-name,Values=running\" --query 'Reservations[0].Instances[0].InstanceId' --output text"
}
