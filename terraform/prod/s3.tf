resource "aws_s3_bucket" "static" {
  bucket = var.static_bucket_name

  tags = {
    Name = "superschedules-prod-static"
  }
}

resource "aws_s3_bucket_public_access_block" "static" {
  bucket                  = aws_s3_bucket.static.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

