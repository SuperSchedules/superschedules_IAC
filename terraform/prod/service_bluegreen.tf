module "service_bluegreen" {
  source = "../../modules/service_bluegreen"

  service     = "superschedules"
  environment = "prod"

  alb_arn = aws_lb.app.arn
  vpc_id  = aws_vpc.main.id

  private_subnet_ids      = [for s in aws_subnet.private : s.id]
  launch_template_id      = aws_launch_template.app.id
  launch_template_version = var.app_launch_template_version

  desired_capacity_blue  = var.blue_desired_capacity
  desired_capacity_green = var.green_desired_capacity
  min_size_blue          = var.blue_min_size
  min_size_green         = var.green_min_size
  max_size_blue          = var.blue_max_size
  max_size_green         = var.green_max_size

  health_check_grace_period = var.app_health_check_grace_period
  health_check_path          = var.health_check_path
  health_check_interval      = var.health_check_interval
  health_check_timeout       = var.health_check_timeout
  health_check_healthy_threshold   = var.health_check_healthy_threshold
  health_check_unhealthy_threshold = var.health_check_unhealthy_threshold
  deregistration_delay             = var.deregistration_delay

  listener_port     = var.listener_port
  listener_protocol = var.listener_protocol
  listener_arn      = var.listener_arn

  active_color               = var.active_color
  traffic_split              = var.traffic_split
  enable_instance_protection = var.enable_instance_protection
  enable_lifecycle_hook      = var.enable_lifecycle_hook
  lifecycle_default_result   = var.lifecycle_default_result
  lifecycle_heartbeat_timeout       = var.lifecycle_heartbeat_timeout
  lifecycle_notification_metadata   = var.lifecycle_notification_metadata
  lifecycle_notification_target_arn = var.lifecycle_notification_target_arn
  lifecycle_notification_role_arn   = var.lifecycle_notification_role_arn

  tags = var.default_tags
}
