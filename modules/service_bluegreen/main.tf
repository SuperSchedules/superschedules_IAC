locals {
  colors = ["blue", "green"]

  target_group_names = {
    for color in local.colors :
    color => format("%s-%s-tg-%s", var.service, var.environment, color)
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

  target_group_tags = {
    for color in local.colors :
    color => merge(
      local.base_tags,
      {
        Name  = local.target_group_names[color]
        Color = color
      }
    )
  }

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
  for_each = toset(local.colors)

  name                 = local.target_group_names[each.key]
  port                 = var.target_group_port
  protocol             = var.target_group_protocol
  target_type          = var.target_type
  vpc_id               = var.vpc_id
  deregistration_delay = var.deregistration_delay

  health_check {
    enabled             = true
    path                = var.health_check_path
    matcher             = var.health_check_matcher
    interval            = var.health_check_interval
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
    timeout             = var.health_check_timeout
  }

  tags = local.target_group_tags[each.key]
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

  target_group_arns = [aws_lb_target_group.this[each.key].arn]

  launch_template {
    id      = var.launch_template_id
    version = var.launch_template_version
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
  listener_target_groups = {
    for color in local.colors :
    color => aws_lb_target_group.this[color].arn
  }

  traffic_split_resolved = length(var.traffic_split) == 0 ? [] : [
    for entry in var.traffic_split :
    {
      color  = entry.tg
      arn    = local.listener_target_groups[entry.tg]
      weight = entry.weight
    }
  ]

  active_color  = var.active_color
  standby_color = local.active_color == "blue" ? "green" : "blue"

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
      target_group_arn = local.listener_target_groups[local.active_color]
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
            arn    = local.listener_target_groups[local.active_color]
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

locals {
  readiness_by_color = {
    for color, asg in aws_autoscaling_group.this :
    color => (
      length(asg.instances) > 0 &&
      alltrue([
        for inst in asg.instances :
        inst.health_status == "Healthy" && contains(["InService"], inst.lifecycle_state)
      ]) &&
      (asg.desired_capacity == null || length(asg.instances) >= asg.desired_capacity)
    )
  }

  ready_to_flip = lookup(local.readiness_by_color, local.standby_color, false)

  active_target_group_arn = local.listener_target_groups[local.active_color]
  active_target_group_name = local.target_group_names[local.active_color]

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
