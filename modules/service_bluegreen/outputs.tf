output "target_group_arns" {
  description = "Map of target group key (color-tgname) to target group ARN."
  value       = { for key, tg in aws_lb_target_group.this : key => tg.arn }
}

output "target_group_names" {
  description = "Map of target group key (color-tgname) to target group name."
  value       = { for key, tg in aws_lb_target_group.this : key => tg.name }
}

output "autoscaling_group_arns" {
  description = "Map of color to Auto Scaling Group ARN."
  value       = { for color, asg in aws_autoscaling_group.this : color => asg.arn }
}

output "autoscaling_group_names" {
  description = "Map of color to Auto Scaling Group name."
  value       = local.autoscaling_group_names
}

output "listener_arn" {
  description = "ARN of the listener managing blue/green traffic."
  value       = local.listener_arn
}

output "active_color" {
  description = "Color currently configured as active."
  value       = local.active_color
}

output "active_target_group" {
  description = "ARN of the default target group currently receiving default traffic."
  value       = local.default_target_groups[local.active_color]
}

output "traffic_split_effective" {
  description = "Effective traffic weighting applied to each color."
  value       = local.traffic_split_resolved
}

output "readiness_by_color" {
  description = "Map indicating whether every instance in each color is in-service and healthy."
  value       = {}  # Removed: instance readiness cannot be determined during plan time
}

output "ready_to_flip" {
  description = "True only if the standby color is completely healthy and ready to receive full traffic."
  value       = local.ready_to_flip
}

output "standby_color" {
  description = "Color that would receive traffic on the next flip."
  value       = local.standby_color
}
