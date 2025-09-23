output "alb_dns_name" {
  description = "Public DNS name of the ALB"
  value       = aws_lb.app.dns_name
}

output "rds_endpoint" {
  description = "RDS Postgres endpoint"
  value       = aws_db_instance.postgres.address
}

output "static_bucket" {
  description = "S3 static bucket name"
  value       = aws_s3_bucket.static.bucket
}
