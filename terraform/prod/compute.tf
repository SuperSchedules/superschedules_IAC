data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

resource "aws_launch_template" "app" {
  name_prefix   = "superschedules-prod-lt-"
  image_id      = data.aws_ami.ubuntu.id
  # instance_type removed - will be specified via mixed_instances_policy in ASG
  user_data     = base64encode(templatefile("${path.module}/templates/user_data.sh.tftpl", {
    region          = var.aws_region,
    aws_account_id  = data.aws_caller_identity.current.account_id,
    nginx_image     = var.nginx_image,
    django_image    = var.django_image,
    fastapi_image   = var.fastapi_image,
    collector_image = var.collector_image,
    db_host         = aws_db_instance.postgres.address,
    db_port         = 5432,
    db_name         = var.db_name,
    db_username     = var.db_username,
    static_bucket   = aws_s3_bucket.static.bucket,
    django_settings_module = var.django_settings_module,
    alb_dns_name    = aws_lb.app.dns_name
  }))

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  vpc_security_group_ids = [aws_security_group.app.id]

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }

  # Note: Spot configuration is handled by mixed_instances_policy in the ASG
  # Do not add instance_market_options here as it conflicts with mixed_instances_policy

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "superschedules-prod-app"
    }
  }
}

