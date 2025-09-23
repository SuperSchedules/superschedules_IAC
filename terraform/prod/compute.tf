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
  instance_type = var.app_instance_type
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
    db_password     = local.db_password_effective,
    static_bucket   = aws_s3_bucket.static.bucket,
    django_settings_module = var.django_settings_module
  }))

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  vpc_security_group_ids = [aws_security_group.app.id]

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "superschedules-prod-app"
    }
  }
}

resource "aws_autoscaling_group" "app" {
  name                      = "superschedules-prod-asg"
  desired_capacity          = 1
  max_size                  = 1
  min_size                  = 1
  vpc_zone_identifier       = [for s in aws_subnet.private : s.id]
  target_group_arns         = [aws_lb_target_group.app.arn]
  health_check_type         = "EC2"
  health_check_grace_period = 120

  launch_template {
    id      = aws_launch_template.app.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "superschedules-prod-app"
    propagate_at_launch = true
  }
}

