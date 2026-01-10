# Lambda function to update Route53 A records when prod-lite instance launches

# Package the Lambda function
data "archive_file" "dns_updater" {
  type        = "zip"
  source_file = "${path.module}/lambda/dns_updater.py"
  output_path = "${path.module}/lambda/dns_updater.zip"
}

# Lambda function
resource "aws_lambda_function" "dns_updater" {
  filename         = data.archive_file.dns_updater.output_path
  function_name    = "${local.name_prefix}-dns-updater"
  role             = aws_iam_role.lambda.arn
  handler          = "dns_updater.handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.dns_updater.output_base64sha256
  timeout          = 60

  environment {
    variables = {
      HOSTED_ZONE_ID = data.aws_route53_zone.main.zone_id
      DOMAINS        = join(",", local.all_domains)
      TTL            = "60"
    }
  }

  tags = {
    Name        = "${local.name_prefix}-dns-updater"
    Environment = "prod-lite"
  }
}

# IAM role for Lambda
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-dns-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Name        = "${local.name_prefix}-dns-lambda-role"
    Environment = "prod-lite"
  }
}

# Basic Lambda execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda permissions for Route53, EC2, and ASG
resource "aws_iam_role_policy" "lambda_permissions" {
  name = "${local.name_prefix}-dns-lambda-permissions"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "route53:ChangeResourceRecordSets"
        ]
        Resource = "arn:aws:route53:::hostedzone/${data.aws_route53_zone.main.zone_id}"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:CompleteLifecycleAction"
        ]
        Resource = aws_autoscaling_group.app.arn
      }
    ]
  })
}

# EventBridge rule to trigger Lambda on ASG instance launch
resource "aws_cloudwatch_event_rule" "asg_launch" {
  name        = "${local.name_prefix}-asg-launch"
  description = "Trigger DNS update when prod-lite instance launches"

  event_pattern = jsonencode({
    source      = ["aws.autoscaling"]
    detail-type = ["EC2 Instance-launch Lifecycle Action"]
    detail = {
      AutoScalingGroupName = [aws_autoscaling_group.app.name]
    }
  })

  tags = {
    Name        = "${local.name_prefix}-asg-launch-rule"
    Environment = "prod-lite"
  }
}

# EventBridge target - invoke Lambda
resource "aws_cloudwatch_event_target" "dns_updater" {
  rule      = aws_cloudwatch_event_rule.asg_launch.name
  target_id = "dns-updater"
  arn       = aws_lambda_function.dns_updater.arn
}

# Allow EventBridge to invoke Lambda
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dns_updater.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.asg_launch.arn
}
