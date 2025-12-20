# CloudWatch Logs configuration for Docker container logging

resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/aws/superschedules/prod/app"
  retention_in_days = 7

  tags = {
    Environment = "production"
    Application = "superschedules"
  }
}

# Log streams are created automatically by the Docker awslogs driver
# One stream per container instance
