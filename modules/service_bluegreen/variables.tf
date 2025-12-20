variable "service" {
  type        = string
  description = "Logical service name used for tagging and resource naming."
}

variable "environment" {
  type        = string
  description = "Deployment environment label (e.g., prod, staging)."
}

variable "alb_arn" {
  type        = string
  description = "ARN of the existing Application Load Balancer."
}

variable "listener_arn" {
  type        = string
  description = "Existing listener ARN to be managed via rules. Leave null to let the module create a listener."
  default     = null
}

variable "listener_port" {
  type        = number
  description = "Port for the managed listener when the module creates it."
  default     = 80
}

variable "listener_protocol" {
  type        = string
  description = "Protocol for the managed listener (HTTP or HTTPS)."
  default     = "HTTP"
}

variable "listener_ssl_policy" {
  type        = string
  description = "Optional SSL policy for HTTPS listeners."
  default     = null
}

variable "listener_certificate_arn" {
  type        = string
  description = "Certificate ARN for HTTPS listeners when the module creates the listener."
  default     = null
}

variable "listener_alpn_policy" {
  type        = string
  description = "Optional ALPN policy for HTTPS listeners."
  default     = null
}

variable "listener_fixed_response" {
  type = object({
    status_code  = string
    content_type = optional(string)
    message_body = optional(string)
  })
  description = "Optional fixed-response configuration applied instead of forwarding."
  default     = null
}

variable "listener_redirect" {
  type = object({
    status_code = optional(string)
    host        = optional(string)
    path        = optional(string)
    port        = optional(string)
    protocol    = optional(string)
    query       = optional(string)
  })
  description = "Optional redirect configuration applied instead of forwarding."
  default     = null
}

variable "listener_weight_rule_priority" {
  type        = number
  description = "Priority for the all-path listener rule when an existing listener ARN is supplied."
  default     = 10
}

variable "vpc_id" {
  type        = string
  description = "VPC identifier used for target groups."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "List of private subnet IDs for the Auto Scaling Groups."
}

variable "launch_template_id" {
  type        = string
  description = "ID of the launch template used by both Auto Scaling Groups."
}

variable "launch_template_version" {
  type        = string
  description = "Launch template version to use (e.g., $Latest)."
  default     = "$Latest"
}

variable "desired_capacity_blue" {
  type        = number
  description = "Desired capacity for the blue Auto Scaling Group."
}

variable "desired_capacity_green" {
  type        = number
  description = "Desired capacity for the green Auto Scaling Group."
}

variable "min_size_blue" {
  type        = number
  description = "Minimum capacity for the blue Auto Scaling Group."
}

variable "min_size_green" {
  type        = number
  description = "Minimum capacity for the green Auto Scaling Group."
}

variable "max_size_blue" {
  type        = number
  description = "Maximum capacity for the blue Auto Scaling Group."
}

variable "max_size_green" {
  type        = number
  description = "Maximum capacity for the green Auto Scaling Group."
}

variable "health_check_grace_period" {
  type        = number
  description = "Grace period in seconds before health checks start evaluating new instances."
  default     = 420
}

variable "target_groups" {
  type = map(object({
    port                     = number
    protocol                 = string
    health_check_path        = string
    health_check_matcher     = optional(string, "200-399")
    deregistration_delay     = optional(number, 180)
    path_patterns            = optional(list(string), [])  # Empty means default action
    listener_rule_priority   = optional(number, null)      # Required if path_patterns is set
  }))
  description = "Map of target group configurations. Key is the target group name suffix (e.g., 'frontend', 'django')"
}

variable "target_type" {
  type        = string
  description = "Target type for the load balancer target groups (instance or ip)."
  default     = "instance"
}

variable "health_check_path" {
  type        = string
  description = "DEPRECATED: Use target_groups[].health_check_path instead. Health check path that reflects full readiness (e.g., /ready)."
  default     = "/ready"
}

variable "health_check_interval" {
  type        = number
  description = "Time between health checks in seconds."
  default     = 30
}

variable "health_check_timeout" {
  type        = number
  description = "Health check timeout in seconds."
  default     = 5
}

variable "health_check_healthy_threshold" {
  type        = number
  description = "Number of consecutive successes required to mark a target healthy."
  default     = 3
}

variable "health_check_unhealthy_threshold" {
  type        = number
  description = "Number of consecutive failures required to mark a target unhealthy."
  default     = 2
}

variable "health_check_matcher" {
  type        = string
  description = "HTTP status codes that represent a successful health check."
  default     = "200-399"
}

variable "deregistration_delay" {
  type        = number
  description = "Time in seconds for existing requests to complete on deregistration."
  default     = 180
}

variable "active_color" {
  type        = string
  description = "Color (blue or green) that should currently receive 100% of traffic unless traffic_split overrides it."
  default     = "blue"

  validation {
    condition     = contains(["blue", "green"], var.active_color)
    error_message = "active_color must be either \"blue\" or \"green\"."
  }
}

variable "traffic_split" {
  type = list(object({
    tg     = string
    weight = number
  }))
  description = "Optional weighted canary definition mapping color names to integer weights."
  default     = []

  validation {
    condition = alltrue([
      for entry in var.traffic_split : contains(["blue", "green"], entry.tg)
    ])
    error_message = "traffic_split entries must reference either blue or green target groups."
  }

  validation {
    condition = length(var.traffic_split) == 0 || sum([
      for entry in var.traffic_split : entry.weight
    ]) == 100
    error_message = "Weighted traffic splits must total 100."
  }
}

variable "enable_instance_protection" {
  type        = bool
  description = "Enable instance protection from scale-in during cutovers."
  default     = false
}

variable "force_delete_asg" {
  type        = bool
  description = "Allow the Auto Scaling Groups to be force deleted."
  default     = false
}

variable "enable_lifecycle_hook" {
  type        = bool
  description = "Whether to create the launch lifecycle hook for blue/green groups."
  default     = true
}

variable "lifecycle_default_result" {
  type        = string
  description = "Default result when the lifecycle hook times out (ABANDON or CONTINUE)."
  default     = "ABANDON"
}

variable "lifecycle_heartbeat_timeout" {
  type        = number
  description = "Seconds before the lifecycle hook times out."
  default     = 900
}

variable "lifecycle_notification_metadata" {
  type        = string
  description = "Optional metadata blob published with lifecycle hook notifications."
  default     = null
}

variable "lifecycle_notification_target_arn" {
  type        = string
  description = "Optional SNS or SQS target for lifecycle notifications."
  default     = null
}

variable "lifecycle_notification_role_arn" {
  type        = string
  description = "IAM role ARN that allows Auto Scaling to publish notifications."
  default     = null
}

variable "tags" {
  type        = map(string)
  description = "Additional tags added to all resources."
  default     = {}
}

variable "additional_instance_tags" {
  type        = map(string)
  description = "Extra tags propagated to instances launched by the Auto Scaling Groups."
  default     = {}
}

variable "instance_types" {
  type        = list(string)
  description = "List of instance types for mixed instances policy. If empty, uses launch template instance type. Example: [\"t3.micro\", \"t3a.micro\", \"t2.micro\"]"
  default     = []
}

variable "spot_allocation_strategy" {
  type        = string
  description = "Strategy for spot instances: lowest-price, capacity-optimized, capacity-optimized-prioritized, or price-capacity-optimized"
  default     = "price-capacity-optimized"
}

variable "on_demand_base_capacity" {
  type        = number
  description = "Minimum number of on-demand instances (rest will be spot)"
  default     = 0
}

variable "on_demand_percentage_above_base" {
  type        = number
  description = "Percentage of on-demand instances above base capacity (0-100)"
  default     = 0
}
