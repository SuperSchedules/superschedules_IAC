# Dedicated Celery Beat + Worker instance (singleton)
# Runs on t3.nano spot (~$1.14/month) with 512MB RAM + swap
# Runs celery beat scheduler + 1 worker to offload main instances

resource "aws_launch_template" "celery_beat" {
  name_prefix   = "superschedules-prod-celery-beat-"
  image_id      = data.aws_ami.ubuntu.id  # Same x86_64 AMI as main instances
  instance_type = "t3.nano"
  user_data     = base64encode(templatefile("${path.module}/templates/celery_beat_user_data.sh.tftpl", {
    region                 = var.aws_region,
    aws_account_id         = data.aws_caller_identity.current.account_id,
    django_image           = var.django_image,
    db_host                = aws_db_instance.postgres.address,
    db_port                = 5432,
    db_name                = var.db_name,
    db_username            = var.db_username,
    django_settings_module = var.django_settings_module
  }))

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  vpc_security_group_ids = [aws_security_group.celery_beat.id]

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_size           = 8  # Minimal disk
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }

  # Spot instance for cost savings (~70% cheaper than on-demand)
  instance_market_options {
    market_type = "spot"
    spot_options {
      max_price = ""  # Use current spot price
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "superschedules-prod-celery-beat"
      Role = "celery-beat"
    }
  }
}

# Security group for celery-beat (no inbound needed, only outbound to DB)
resource "aws_security_group" "celery_beat" {
  name        = "superschedules-prod-celery-beat-sg"
  description = "Celery Beat security group"
  vpc_id      = aws_vpc.main.id

  # No inbound rules needed - beat doesn't listen on any ports

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "superschedules-prod-celery-beat-sg"
  }
}

# ASG with exactly 1 instance (singleton)
resource "aws_autoscaling_group" "celery_beat" {
  name                = "superschedules-prod-celery-beat-asg"
  vpc_zone_identifier = [for subnet in aws_subnet.public : subnet.id]
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1

  launch_template {
    id      = aws_launch_template.celery_beat.id
    version = "$Latest"
  }

  health_check_type         = "EC2"
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "superschedules-prod-celery-beat"
    propagate_at_launch = true
  }

  tag {
    key                 = "Role"
    value               = "celery-beat"
    propagate_at_launch = true
  }
}
