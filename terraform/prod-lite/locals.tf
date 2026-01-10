locals {
  name_prefix = "superschedules-prod-lite"

  # All domains this instance will serve
  all_domains = [
    var.api_domain,
    var.www_domain,
    var.admin_domain,
    var.apex_domain
  ]

  # CloudWatch log group
  log_group = "/aws/superschedules/prod-lite/app"
}
