variable "aws_region" {
  description = "AWS region for prod resources"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs"
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

# private_subnet_cidrs removed - no longer using private subnets

variable "app_instance_type" {
  description = "EC2 instance type for app"
  type        = string
  default     = "t3.micro"
}

variable "blue_desired_capacity" {
  description = "Desired capacity for the blue Auto Scaling Group"
  type        = number
  default     = 1
}

variable "blue_min_size" {
  description = "Minimum capacity for the blue Auto Scaling Group"
  type        = number
  default     = 1
}

variable "blue_max_size" {
  description = "Maximum capacity for the blue Auto Scaling Group"
  type        = number
  default     = 2
}

variable "green_desired_capacity" {
  description = "Desired capacity for the green Auto Scaling Group"
  type        = number
  default     = 0
}

variable "green_min_size" {
  description = "Minimum capacity for the green Auto Scaling Group"
  type        = number
  default     = 0
}

variable "green_max_size" {
  description = "Maximum capacity for the green Auto Scaling Group"
  type        = number
  default     = 2
}

variable "app_launch_template_version" {
  description = "Launch template version to use for blue/green groups"
  type        = string
  default     = "$Latest"
}

variable "app_health_check_grace_period" {
  description = "Seconds to ignore unhealthy checks after an instance launches"
  type        = number
  default     = 420
}

variable "nginx_image" {
  description = "ECR image URI:tag for Nginx"
  type        = string
}

variable "django_image" {
  description = "ECR image URI:tag for Django"
  type        = string
}

variable "fastapi_image" {
  description = "ECR image URI:tag for FastAPI"
  type        = string
}

variable "collector_image" {
  description = "ECR image URI:tag for Collector"
  type        = string
}

variable "django_settings_module" {
  description = "Python path to Django settings module"
  type        = string
  default     = "config.settings.production"
}

variable "db_engine_version" {
  description = "Postgres engine version"
  type        = string
  default     = "15"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "superschedules"
}

variable "db_username" {
  description = "Database username"
  type        = string
  default     = "superschedules"
}

variable "db_password" {
  description = "Database password (optional; generated if unset)"
  type        = string
  default     = null
  sensitive   = true
}

variable "static_bucket_name" {
  description = "S3 bucket name for static files"
  type        = string
}

variable "health_check_path" {
  description = "ALB health check path"
  type        = string
  default     = "/ready"
}

variable "health_check_interval" {
  description = "Seconds between ALB health checks"
  type        = number
  default     = 20  # Faster checks to bring instances up quicker
}

variable "health_check_timeout" {
  description = "Timeout in seconds for ALB health checks"
  type        = number
  default     = 10  # Longer timeout to account for Django startup
}

variable "health_check_healthy_threshold" {
  description = "Consecutive successes before a target is marked healthy"
  type        = number
  default     = 2  # Reduced from 3 to speed up healthy marking
}

variable "health_check_unhealthy_threshold" {
  description = "Consecutive failures before a target is marked unhealthy"
  type        = number
  default     = 2
}

variable "deregistration_delay" {
  description = "Seconds to wait for in-flight requests before deregistering targets"
  type        = number
  default     = 180
}

variable "listener_port" {
  description = "Port for the HTTP listener"
  type        = number
  default     = 80
}

variable "listener_protocol" {
  description = "Protocol for the ALB listener"
  type        = string
  default     = "HTTP"
}

variable "listener_arn" {
  description = "Existing listener ARN (optional). Leave null to let Terraform manage the listener."
  type        = string
  default     = null
}

variable "active_color" {
  description = "Color currently serving production traffic"
  type        = string
  default     = "blue"

  validation {
    condition     = contains(["blue", "green"], var.active_color)
    error_message = "active_color must be either \"blue\" or \"green\"."
  }
}

variable "traffic_split" {
  description = "Weighted blue/green traffic split"
  type = list(object({
    tg     = string
    weight = number
  }))
  default = []

  validation {
    condition = alltrue([
      for entry in var.traffic_split : contains(["blue", "green"], entry.tg)
    ])
    error_message = "traffic_split entries must reference the blue or green target group."
  }

  validation {
    condition = length(var.traffic_split) == 0 || sum([
      for entry in var.traffic_split : entry.weight
    ]) == 100
    error_message = "traffic_split weights must sum to 100."
  }
}

variable "enable_instance_protection" {
  description = "Enable instance protection from scale-in during cutovers"
  type        = bool
  default     = false
}

variable "enable_lifecycle_hook" {
  description = "Create the lifecycle hook that pauses instances until setup completes"
  type        = bool
  default     = true
}

variable "lifecycle_default_result" {
  description = "Lifecycle hook default result when the heartbeat times out"
  type        = string
  default     = "CONTINUE"
}

variable "lifecycle_heartbeat_timeout" {
  description = "Seconds before the lifecycle hook times out"
  type        = number
  default     = 300  # 5 minutes - enough time for instance to boot and pass health checks
}

variable "lifecycle_notification_metadata" {
  description = "Optional metadata blob for lifecycle hook notifications"
  type        = string
  default     = null
}

variable "lifecycle_notification_target_arn" {
  description = "Optional SNS or SQS ARN for lifecycle notifications"
  type        = string
  default     = null
}

variable "lifecycle_notification_role_arn" {
  description = "IAM role ARN allowing lifecycle notifications"
  type        = string
  default     = null
}

variable "default_tags" {
  description = "Tags merged into all module-managed resources"
  type        = map(string)
  default     = {}
}
