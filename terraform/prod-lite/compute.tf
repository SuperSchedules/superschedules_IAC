# AMI selection - custom or stock Ubuntu 22.04
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  ami_id = var.use_custom_ami ? var.custom_ami_id : data.aws_ami.ubuntu.id
}

# Launch Template for prod-lite instance
resource "aws_launch_template" "app" {
  name_prefix   = "${local.name_prefix}-lt-"
  image_id      = local.ami_id
  instance_type = var.instance_type

  user_data = base64encode(templatefile("${path.module}/templates/user_data_prod_lite.sh.tftpl", {
    region                  = var.aws_region
    secrets_id              = var.secrets_manager_id
    backend_repo_url        = var.backend_repo_url
    frontend_repo_url       = var.frontend_repo_url
    backend_branch          = var.backend_branch
    frontend_branch         = var.frontend_branch
    db_host                 = data.aws_db_instance.postgres.address
    db_port                 = 5432
    db_name                 = var.db_name
    db_username             = var.db_username
    django_settings_module  = var.django_settings_module
    gunicorn_workers        = var.gunicorn_workers
    celery_concurrency      = var.celery_concurrency
    static_bucket           = var.static_bucket_name
    data_bucket             = var.data_bucket_name
    certbot_email           = var.certbot_email
    api_domain              = var.api_domain
    www_domain              = var.www_domain
    admin_domain            = var.admin_domain
    apex_domain             = var.apex_domain
    all_domains             = join(" ", local.all_domains)
    vite_api_base_url       = var.vite_api_base_url
    vite_turnstile_site_key = var.vite_turnstile_site_key
    log_group               = local.log_group
    use_custom_ami          = var.use_custom_ami
  }))

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  vpc_security_group_ids = [aws_security_group.app.id]

  # SSH key pair (optional - not needed if using SSM)
  key_name = var.ssh_key_name != "" ? var.ssh_key_name : null

  # EBS root volume - larger for source code, node_modules, venv
  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }

  # Spot instance configuration
  instance_market_options {
    market_type = "spot"
    spot_options {
      max_price = "" # Use current spot price (no cap)
    }
  }

  # Metadata options (IMDSv2 for security)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name        = local.name_prefix
      Environment = "prod-lite"
      Role        = "app"
    }
  }

  tag_specifications {
    resource_type = "volume"
    tags = {
      Name        = "${local.name_prefix}-volume"
      Environment = "prod-lite"
    }
  }

  tags = {
    Name        = "${local.name_prefix}-lt"
    Environment = "prod-lite"
  }
}

# Auto Scaling Group - exactly 1 instance
resource "aws_autoscaling_group" "app" {
  name                = "${local.name_prefix}-asg"
  vpc_zone_identifier = data.aws_subnets.public.ids
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  health_check_type         = "EC2"
  health_check_grace_period = 600 # 10 min for full bootstrap

  # Enable capacity rebalancing for spot interruptions
  capacity_rebalance = true

  # Lifecycle hook to trigger DNS update Lambda
  initial_lifecycle_hook {
    name                 = "dns-update-hook"
    default_result       = "CONTINUE"
    heartbeat_timeout    = 300
    lifecycle_transition = "autoscaling:EC2_INSTANCE_LAUNCHING"
  }

  tag {
    key                 = "Name"
    value               = local.name_prefix
    propagate_at_launch = true
  }

  tag {
    key                 = "Environment"
    value               = "prod-lite"
    propagate_at_launch = true
  }

  tag {
    key                 = "Role"
    value               = "app"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }
}
