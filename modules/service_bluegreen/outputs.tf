output "target_group_arns" {
  description = "Map of color to target group ARN."
  value       = { for color in local.colors : color => aws_lb_target_group.this[color].arn }
}

output "target_group_names" {
  description = "Map of color to target group name."
  value       = local.target_group_names
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
  description = "Details for the target group currently receiving default traffic."
  value = {
    arn  = local.active_target_group_arn
    name = local.active_target_group_name
  }
}

output "traffic_split_effective" {
  description = "Effective traffic weighting applied to each color."
  value       = local.traffic_split_effective
}

output "readiness_by_color" {
  description = "Map indicating whether every instance in each color is in-service and healthy."
  value       = local.readiness_by_color
}

output "ready_to_flip" {
  description = "True only if the standby color is completely healthy and ready to receive full traffic."
  value       = local.ready_to_flip
}

output "standby_color" {
  description = "Color that would receive traffic on the next flip."
  value       = local.standby_color
}
