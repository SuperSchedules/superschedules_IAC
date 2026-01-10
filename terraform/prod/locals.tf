# Local values for computed configuration

locals {
  # ECR registry base URL
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"

  # Build image URIs from tags, with fallback to legacy full URI variables
  django_image = coalesce(
    var.django_image,
    "${local.ecr_registry}/superschedules-api:${var.api_image_tag}"
  )

  nginx_image = coalesce(
    var.nginx_image,
    "${local.ecr_registry}/superschedules-frontend:${var.frontend_image_tag}"
  )
}
