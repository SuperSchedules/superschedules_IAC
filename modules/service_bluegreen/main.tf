locals {
  colors = ["blue", "green"]

  # Create a flat map of all target group combinations (color + tg_name)
  all_target_groups = flatten([
    for color in local.colors : [
      for tg_name, tg_config in var.target_groups : {
        key       = "${color}-${tg_name}"
        color     = color
        tg_name   = tg_name
        tg_config = tg_config
      }
    ]
  ])

  target_groups_map = {
    for tg in local.all_target_groups :
    tg.key => tg
  }

  autoscaling_group_names = {
    for color in local.colors :
    color => format("%s-%s-asg-%s", var.service, var.environment, color)
  }

  base_tags = merge(
    {
      Service     = var.service
      Environment = var.environment
    },
    var.tags
  )

  autoscaling_tags = {
    for color in local.colors :
    color => merge(
      local.base_tags,
      {
        Name  = local.autoscaling_group_names[color]
        Color = color
      }
    )
  }
}

resource "aws_lb_target_group" "this" {
  for_each = local.target_groups_map

  # Use shorter name format to stay under 32 char limit
  name                 = format("%s-%s-%s-%s", substr(var.service, 0, 10), var.environment, each.value.tg_name, each.value.color)
  port                 = each.value.tg_config.port
  protocol             = each.value.tg_config.protocol
  target_type          = var.target_type
  vpc_id               = var.vpc_id
  deregistration_delay = each.value.tg_config.deregistration_delay

  health_check {
    enabled             = true
    path                = each.value.tg_config.health_check_path
    matcher             = each.value.tg_config.health_check_matcher
    interval            = var.health_check_interval
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
    timeout             = var.health_check_timeout
  }

  tags = merge(
    local.base_tags,
    {
      Name  = format("%s-%s-%s-%s", var.service, var.environment, each.value.tg_name, each.value.color)
      Color = each.value.color
      TargetGroup = each.value.tg_name
    }
  )
}

resource "aws_autoscaling_group" "this" {
  for_each = {
    for color in local.colors :
    color => {
      desired_capacity = color == "blue" ? var.desired_capacity_blue : var.desired_capacity_green
      min_size         = color == "blue" ? var.min_size_blue : var.min_size_green
      max_size         = color == "blue" ? var.max_size_blue : var.max_size_green
    }
  }

  name                      = local.autoscaling_group_names[each.key]
  desired_capacity          = each.value.desired_capacity
  min_size                  = each.value.min_size
  max_size                  = each.value.max_size
  vpc_zone_identifier       = var.private_subnet_ids
  health_check_type         = "ELB"
  health_check_grace_period = var.health_check_grace_period
  capacity_rebalance    = true
  force_delete          = var.force_delete_asg
  protect_from_scale_in = var.enable_instance_protection

  # Attach all target groups for this color
  target_group_arns = [
    for tg_key, tg in aws_lb_target_group.this :
    tg.arn if local.target_groups_map[tg_key].color == each.key
  ]

  # Use mixed instances policy if instance_types is provided, otherwise use simple launch template
  dynamic "mixed_instances_policy" {
    for_each = length(var.instance_types) > 0 ? [1] : []

    content {
      launch_template {
        launch_template_specification {
          launch_template_id = var.launch_template_id
          version            = var.launch_template_version
        }

        dynamic "override" {
          for_each = var.instance_types
          content {
            instance_type = override.value
          }
        }
      }

      instances_distribution {
        on_demand_base_capacity                  = var.on_demand_base_capacity
        on_demand_percentage_above_base_capacity = var.on_demand_percentage_above_base
        spot_allocation_strategy                 = var.spot_allocation_strategy
      }
    }
  }

  # Fallback to simple launch template if no instance_types specified
  dynamic "launch_template" {
    for_each = length(var.instance_types) == 0 ? [1] : []

    content {
      id      = var.launch_template_id
      version = var.launch_template_version
    }
  }

  dynamic "tag" {
    for_each = merge(
      local.autoscaling_tags[each.key],
      var.additional_instance_tags
    )

    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

}

resource "aws_autoscaling_lifecycle_hook" "launching" {
  for_each = var.enable_lifecycle_hook ? aws_autoscaling_group.this : {}

  name                    = format("%s-%s-%s-launch", var.service, var.environment, each.key)
  autoscaling_group_name  = each.value.name
  lifecycle_transition    = "autoscaling:EC2_INSTANCE_LAUNCHING"
  default_result          = var.lifecycle_default_result
  heartbeat_timeout       = var.lifecycle_heartbeat_timeout
  notification_metadata   = var.lifecycle_notification_metadata
  notification_target_arn = var.lifecycle_notification_target_arn
  role_arn                = var.lifecycle_notification_role_arn
}

locals {
  active_color  = var.active_color
  standby_color = local.active_color == "blue" ? "green" : "blue"

  # Find the default target group (one with no path_patterns) for each color
  default_tg_key = [
    for tg_name, tg_config in var.target_groups :
    tg_name if length(tg_config.path_patterns) == 0
  ][0]

  # Get ARNs for default target groups by color
  default_target_groups = {
    for color in local.colors :
    color => aws_lb_target_group.this["${color}-${local.default_tg_key}"].arn
  }

  # Build traffic split for default target groups
  traffic_split_resolved = length(var.traffic_split) == 0 ? [] : [
    for entry in var.traffic_split :
    {
      color  = entry.tg
      arn    = local.default_target_groups[entry.tg]
      weight = entry.weight
    }
  ]

  listener_mode = var.listener_fixed_response != null ? "fixed" : (
    var.listener_redirect != null ? "redirect" : (
      length(local.traffic_split_resolved) == 0 ? "forward" : "weighted"
    )
  )

  listener_arn = var.listener_arn == null ? aws_lb_listener.this[0].arn : var.listener_arn
}

resource "aws_lb_listener" "this" {
  count             = var.listener_arn == null ? 1 : 0
  load_balancer_arn = var.alb_arn
  port              = var.listener_port
  protocol          = var.listener_protocol

  dynamic "default_action" {
    for_each = local.listener_mode == "forward" ? [true] : []
    content {
      type             = "forward"
      target_group_arn = local.default_target_groups[local.active_color]
    }
  }

  dynamic "default_action" {
    for_each = local.listener_mode == "weighted" ? [true] : []
    content {
      type = "forward"

      forward {
        dynamic "target_group" {
          for_each = local.traffic_split_resolved
          content {
            arn    = target_group.value.arn
            weight = target_group.value.weight
          }
        }
      }
    }
  }

  dynamic "default_action" {
    for_each = local.listener_mode == "fixed" ? [var.listener_fixed_response] : []
    content {
      type = "fixed-response"

      fixed_response {
        content_type = lookup(default_action.value, "content_type", "text/plain")
        message_body = lookup(default_action.value, "message_body", null)
        status_code  = default_action.value.status_code
      }
    }
  }

  dynamic "default_action" {
    for_each = local.listener_mode == "redirect" ? [var.listener_redirect] : []
    content {
      type = "redirect"

      redirect {
        status_code = lookup(default_action.value, "status_code", "HTTP_302")
        port        = lookup(default_action.value, "port", null)
        protocol    = lookup(default_action.value, "protocol", null)
        host        = lookup(default_action.value, "host", null)
        path        = lookup(default_action.value, "path", null)
        query       = lookup(default_action.value, "query", null)
      }
    }
  }

  ssl_policy      = var.listener_ssl_policy
  certificate_arn = var.listener_certificate_arn
  alpn_policy     = var.listener_alpn_policy

  tags = merge(local.base_tags, {
    Name = format("%s-%s-listener", var.service, var.environment)
  })
}

resource "aws_lb_listener_rule" "weights" {
  count        = var.listener_arn == null ? 0 : 1
  listener_arn = var.listener_arn
  priority     = var.listener_weight_rule_priority

  action {
    type = "forward"

    forward {
      dynamic "target_group" {
        for_each = length(local.traffic_split_resolved) == 0 ? [
          {
            arn    = local.default_target_groups[local.active_color]
            weight = 1
          }
        ] : local.traffic_split_resolved

        content {
          arn    = target_group.value.arn
          weight = target_group.value.weight
        }
      }
    }
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Path-based routing rules for non-default target groups
# Uses stable resource keys (e.g., "django") and dynamically references active color's target group
# This allows in-place updates during blue-green flips instead of destroy+create
resource "aws_lb_listener_rule" "path_routes" {
  for_each = {
    for tg_name, tg_config in var.target_groups :
    tg_name => tg_config if length(tg_config.path_patterns) > 0
  }

  listener_arn = local.listener_arn
  priority     = each.value.listener_rule_priority

  action {
    type             = "forward"
    # Dynamic reference to active color's target group - updates in-place when active_color changes
    target_group_arn = aws_lb_target_group.this["${local.active_color}-${each.key}"].arn
  }

  condition {
    path_pattern {
      values = each.value.path_patterns
    }
  }

  tags = merge(
    local.base_tags,
    {
      Name = "${var.service}-${var.environment}-${each.key}-path-routing"
    }
  )
}

locals {
  # Note: Instance readiness cannot be determined during plan time
  # Use external monitoring or CI/CD checks to verify deployment readiness
  ready_to_flip = false

  traffic_split_effective = length(local.traffic_split_resolved) == 0 ? [
    {
      color  = local.active_color
      weight = 100
    }
  ] : [
    for entry in local.traffic_split_resolved :
    {
      color  = entry.color
      weight = entry.weight
    }
  ]
}
