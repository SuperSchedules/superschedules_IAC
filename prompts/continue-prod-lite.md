# Continue: Prod-Lite Implementation

## What Was Done

We created a new **prod-lite** environment - a non-Docker, fast-deploy alternative to the existing Docker+ALB prod setup.

### Files Created

```
terraform/prod-lite/
├── backend.tf              # S3 state backend
├── provider.tf             # AWS provider with assume role
├── main.tf                 # Data sources (VPC, RDS, Route53, subnets)
├── variables.tf            # All input variables
├── locals.tf               # Computed values (domains, naming)
├── iam.tf                  # EC2 role (SSM, Secrets, S3, SQS, Bedrock, CloudWatch)
├── security_group.tf       # HTTP/HTTPS ports, RDS access rule
├── compute.tf              # Launch template + ASG (t3.medium spot, desired=1)
├── dns_lambda.tf           # Lambda + EventBridge to update Route53 on instance launch
├── outputs.tf              # URLs, commands, instance info
├── lambda/dns_updater.py   # Python Lambda that updates Route53 A records
├── templates/user_data_prod_lite.sh.tftpl  # Full bootstrap script
└── terraform.tfvars.example

scripts/deploy-prod-lite.sh  # Standalone SSM-based deploy script
```

### Key Design Decisions

1. **No Docker** - gunicorn, celery-worker, celery-beat run directly via systemd
2. **No ALB** - nginx + Let's Encrypt on the instance for TLS
3. **No SSH keys** - uses SSM Session Manager for access
4. **Spot instance** - t3.medium (~$15-20/mo vs ~$50-80/mo for prod)
5. **Shares with prod** - same RDS, SQS queues, Secrets Manager, VPC
6. **Production domains** - api.eventzombie.com, www.eventzombie.com, admin.eventzombie.com, eventzombie.com

### Deploy Manager Updates

Added `lite` command group to `deploy_manager/deploy_manager/cli.py`:
- `deploy-manager lite status` - show instance info
- `deploy-manager lite deploy [-s backend|frontend|all]` - fast deploy via SSM
- `deploy-manager lite shell` - open SSM session
- `deploy-manager lite logs [-f] [-s service]` - tail CloudWatch logs
- `deploy-manager lite services` - check systemd service status

### Makefile Targets

- `make prod-lite-init/plan/apply/destroy`
- `make prod-lite-deploy` / `make prod-lite-deploy-backend` / `make prod-lite-deploy-frontend`
- `make prod-lite-shell`
- `make prod-lite-status`
- `make prod-lite-logs`

### RDS Protection

Changed `terraform/prod/rds.tf`:
- `deletion_protection = true` (was false)
- `skip_final_snapshot = false` (was true)

**User needs to apply this**: `cd terraform/prod && terraform apply -target=aws_db_instance.postgres`

## What's NOT Done Yet

### 1. Deploy Manager System Flipping
The user mentioned wanting the deploy-manager to:
- Know which system is "active" (prod vs prod-lite)
- Flip DNS between ALB and direct instance
- Show different commands based on active system

This was identified as a separate task needing proper planning.

### 2. Testing
Prod-lite hasn't been deployed yet. User needs to:
```bash
cd terraform/prod-lite
echo 'certbot_email = "your@email.com"' > terraform.tfvars
terraform init
terraform apply
```

### 3. Transition from Prod to Prod-Lite
When ready to switch:
1. Apply RDS deletion protection (mentioned above)
2. Deploy prod-lite
3. Wait for bootstrap (~10 min)
4. Test endpoints
5. Then destroy or scale down prod ALB stack

## Important Context

- Domain is `eventzombie.com` (not superschedules.com)
- RDS identifier: `superschedules-prod-postgres`
- VPC: `superschedules-prod-vpc`
- Secrets: `prod/superschedules/secrets`
- The repos are public HTTPS (no SSH keys needed for git clone)

## Commands to Verify Setup

```bash
# List all prod-lite terraform files
ls -la terraform/prod-lite/

# Check the user_data template
head -50 terraform/prod-lite/templates/user_data_prod_lite.sh.tftpl

# Verify deploy-manager lite commands exist
cd deploy_manager && python -m deploy_manager.cli lite --help
```
