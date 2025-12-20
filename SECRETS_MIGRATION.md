# Secrets Manager Migration

## Overview
Migrated from hardcoded secrets in Terraform to AWS Secrets Manager for improved security.

## Secret ARN
```
arn:aws:secretsmanager:us-east-1:353130947195:secret:prod/superschedules/secrets-kduEg2
```

## Secret Contents
```json
{
  "DB_PASSWORD": "<generated-password>",
  "DJANGO_SECRET_KEY": "<generated-key>",
  "EMAIL_HOST_USER": "<ses-smtp-username>",
  "EMAIL_HOST_PASSWORD": "<ses-smtp-password>"
}
```

## Changes Made

### 1. IAM Policy (terraform/prod/iam.tf)
- Added `secrets_access` policy to allow EC2 instances to read secrets
- Attached policy to EC2 role

### 2. User Data Script (terraform/prod/templates/user_data.sh.tftpl)
- Added secrets fetch from AWS Secrets Manager on instance boot
- Uses `jq` to parse JSON secrets
- Environment variables now use `$$` to escape in heredoc
- Added email configuration environment variables

### 3. Compute Template (terraform/prod/compute.tf)
- Removed `db_password` parameter (now fetched from Secrets Manager)

### 4. Docker Compose Environment
Updated all services to use secrets:
- Django: Uses `DJANGO_SECRET_KEY`, `DB_PASSWORD`, email credentials
- Collector: Uses `DB_PASSWORD` in DATABASE_URL
- Navigator: Uses `DB_PASSWORD`

## Migration Steps

### IMPORTANT: Update RDS Password First!

**Before deploying Terraform changes**, you need to update the RDS database password to match the one in Secrets Manager, or your application will lose database access.

#### Option A: Update RDS password to match secret (Recommended)
```bash
# Get the password from Secrets Manager
DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id prod/superschedules/secrets \
  --query SecretString \
  --output text | jq -r '.DB_PASSWORD')

# Update RDS password
aws rds modify-db-instance \
  --db-instance-identifier superschedules-prod-postgres \
  --master-user-password "$DB_PASSWORD" \
  --apply-immediately

# Wait for modification to complete (takes 2-5 minutes)
aws rds wait db-instance-available \
  --db-instance-identifier superschedules-prod-postgres

echo "RDS password updated successfully"
```

#### Option B: Update secret to match current RDS password
```bash
# Get current Terraform-managed password
cd terraform/prod
terraform output -raw db_password  # If you have an output for this

# Update the secret with current password
aws secretsmanager update-secret \
  --secret-id prod/superschedules/secrets \
  --secret-string '{
    "DB_PASSWORD": "<current-terraform-password>",
    "DJANGO_SECRET_KEY": "<your-django-key>",
    "EMAIL_HOST_USER": "<your-ses-username>",
    "EMAIL_HOST_PASSWORD": "<your-ses-password>"
  }'
```

### Deployment Steps

1. **Apply Terraform changes**
```bash
cd terraform/prod
terraform plan  # Review changes
terraform apply
```

Expected changes:
- Create IAM policy for Secrets Manager access
- Attach policy to EC2 role
- Update launch template with new user_data

2. **Trigger instance refresh** (if using Auto Scaling Group)
```bash
# The launch template version will auto-increment
# New instances will fetch secrets from Secrets Manager

# If needed, manually terminate instances to force refresh
# (Blue/green deployment will handle this)
```

3. **Verify secrets are being used**
```bash
# SSH to an EC2 instance
aws ssm start-session --target <instance-id>

# Check if secrets were fetched
docker exec $(docker ps -qf "name=django") env | grep -E "DJANGO_SECRET_KEY|DB_PASSWORD|EMAIL_HOST"

# Should show environment variables (password values will be masked)
```

## Rollback Plan

If something goes wrong:

1. **Revert Terraform changes**
```bash
git revert <commit-hash>
terraform apply
```

2. **RDS password is unchanged** - database access won't be affected if you updated RDS password first

## Security Benefits

✅ Secrets no longer in Terraform state file
✅ Secrets can be rotated without infrastructure changes
✅ IAM-controlled access with audit trail
✅ Encrypted at rest in Secrets Manager
✅ No secrets in git repository

## Cost

- AWS Secrets Manager: $0.40/month per secret
- API calls: $0.05 per 10,000 calls
- Estimated monthly cost: **$0.40** (single secret, ~1 API call per instance boot)

## Future Improvements

- [ ] Set up automatic secret rotation for DB password
- [ ] Add CloudWatch alarms for failed secret retrievals
- [ ] Consider adding more secrets (third-party API keys, etc.)
- [ ] Implement secret versioning strategy

---
**Created:** 2025-12-08
**Secret ARN:** arn:aws:secretsmanager:us-east-1:353130947195:secret:prod/superschedules/secrets-kduEg2
