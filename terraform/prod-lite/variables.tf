# AWS Region
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# Instance Configuration
variable "instance_type" {
  description = "EC2 instance type (t3.medium for 4GB RAM needed for sentence-transformers)"
  type        = string
  default     = "t3.medium"
}

variable "use_custom_ami" {
  description = "Use custom AMI instead of stock Ubuntu (for faster boot)"
  type        = bool
  default     = false
}

variable "custom_ami_id" {
  description = "Custom AMI ID (required if use_custom_ami is true)"
  type        = string
  default     = ""
}

variable "ssh_key_name" {
  description = "Name of SSH key pair in AWS (optional - not needed if using SSM)"
  type        = string
  default     = ""
}

variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed to SSH (optional - not needed if using SSM)"
  type        = list(string)
  default     = []
}

# Domain Configuration
variable "domain_zone" {
  description = "Route53 hosted zone domain"
  type        = string
  default     = "eventzombie.com"
}

variable "api_domain" {
  description = "API subdomain"
  type        = string
  default     = "api.eventzombie.com"
}

variable "www_domain" {
  description = "Frontend subdomain"
  type        = string
  default     = "www.eventzombie.com"
}

variable "admin_domain" {
  description = "Admin subdomain"
  type        = string
  default     = "admin.eventzombie.com"
}

variable "apex_domain" {
  description = "Apex domain (eventzombie.com without www)"
  type        = string
  default     = "eventzombie.com"
}

variable "certbot_email" {
  description = "Email for Let's Encrypt certificate notifications"
  type        = string
}

# Git Repository Configuration
variable "backend_repo_url" {
  description = "Git URL for backend repository (public, HTTPS)"
  type        = string
  default     = "https://github.com/SuperSchedules/superschedules.git"
}

variable "frontend_repo_url" {
  description = "Git URL for frontend repository (public, HTTPS)"
  type        = string
  default     = "https://github.com/SuperSchedules/superschedules_frontend.git"
}

variable "backend_branch" {
  description = "Git branch for backend"
  type        = string
  default     = "main"
}

variable "frontend_branch" {
  description = "Git branch for frontend"
  type        = string
  default     = "main"
}

# Database Configuration (shared with prod)
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

# Secrets Manager
variable "secrets_manager_id" {
  description = "Secrets Manager secret ID for app secrets"
  type        = string
  default     = "prod/superschedules/secrets"
}

# Django Configuration
variable "django_settings_module" {
  description = "Django settings module"
  type        = string
  default     = "config.settings"
}

# Application Server Configuration
variable "gunicorn_workers" {
  description = "Number of gunicorn workers"
  type        = number
  default     = 3
}

variable "celery_concurrency" {
  description = "Celery worker concurrency"
  type        = number
  default     = 2
}

# S3 Buckets (shared with prod)
variable "static_bucket_name" {
  description = "S3 bucket for Django static files"
  type        = string
  default     = "superschedules-prod-static-us-east-1"
}

variable "data_bucket_name" {
  description = "S3 bucket for census data"
  type        = string
  default     = "superschedules-data"
}

# Frontend Build Configuration
variable "vite_api_base_url" {
  description = "API base URL for frontend build (VITE_API_BASE_URL)"
  type        = string
  default     = "https://api.eventzombie.com"
}

variable "vite_turnstile_site_key" {
  description = "Cloudflare Turnstile site key for frontend (VITE_TURNSTILE_SITE_KEY)"
  type        = string
  default     = "0x4AAAAAACHOkJ0SEFVIkN27"
}
