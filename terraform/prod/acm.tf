# ACM wildcard certificate for *.eventzombie.com and eventzombie.com
# Using direct ARN since terraform user doesn't have acm:ListCertificates permission
locals {
  eventzombie_certificate_arn = "arn:aws:acm:us-east-1:353130947195:certificate/e713716b-38f8-4fe8-9c75-f678b09fde7e"
}
