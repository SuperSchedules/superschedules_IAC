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

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "app_instance_type" {
  description = "EC2 instance type for app"
  type        = string
  default     = "t3.small"
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
  default     = "/"
}
