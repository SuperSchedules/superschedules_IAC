# Superschedules IAC

Terraform infrastructure for the Superschedules platform on AWS. Manages EC2 instances, ALB, RDS, ECR, SQS, and supporting resources.

## Environments

### Prod (Docker + ALB)
- Blue/green deployment with ALB
- Docker containers for all services
- ~11 minute deploy cycle (build → push → ASG refresh)
- Cost: ~$50-80/month

### Prod-Lite (Non-Docker, Fast Deploys)
- Single t3.medium spot instance
- No Docker - runs gunicorn/celery directly via systemd
- nginx + Let's Encrypt for TLS (no ALB)
- ~30 second deploys via SSM
- Cost: ~$15-20/month

## Architecture Overview

### Prod Architecture
```
┌─────────────────────────────────────────────────────────────────────────┐
│  ALB (supersched-prod-alb)                                              │
│    ├── /api/* → Django Target Group (blue/green)                        │
│    └── /* → Frontend Target Group (blue/green)                          │
│                                                                          │
│  EC2 Instances                                                           │
│    ├── superschedules-prod-asg-{blue|green} (t2.small)                  │
│    │     └── Docker: frontend (nginx) + django + celery-worker          │
│    └── superschedules-prod-celery-beat (t3.small)                       │
│          └── Docker: celery-beat + celery-worker                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Prod-Lite Architecture
```
┌─────────────────────────────────────────────────────────────────────────┐
│  Route53 DNS → Instance Public IP (Lambda updates on launch)            │
│    ├── api.eventzombie.com                                              │
│    ├── www.eventzombie.com                                              │
│    ├── admin.eventzombie.com                                            │
│    └── eventzombie.com (redirects to www)                               │
│                                                                          │
│  EC2 Instance (t3.medium spot)                                          │
│    ├── nginx (TLS via Let's Encrypt)                                    │
│    │     ├── api/admin → proxy to gunicorn:8000                         │
│    │     └── www → serve static files from /opt/frontend/dist           │
│    ├── gunicorn (Django + FastAPI)                                      │
│    ├── celery-worker (all queues)                                       │
│    └── celery-beat (scheduler)                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Shared Resources (Both Environments)
```
│  RDS PostgreSQL (superschedules-prod)                                   │
│    └── pgvector extension enabled, deletion_protection = true           │
│                                                                          │
│  SQS Queues (Celery broker)                                             │
│    ├── superschedules-prod-default                                       │
│    ├── superschedules-prod-embeddings                                    │
│    ├── superschedules-prod-geocoding                                     │
│    └── superschedules-prod-scraping                                      │
│                                                                          │
│  Secrets Manager: prod/superschedules/secrets                           │
│  S3: superschedules-prod-static-us-east-1, superschedules-data          │
```

## Prod-Lite Quick Start

```bash
# 1. Create terraform.tfvars
cd terraform/prod-lite
echo 'certbot_email = "your@email.com"' > terraform.tfvars

# 2. Deploy infrastructure
terraform init
terraform apply

# 3. Wait ~10 min for bootstrap, then deploy
make prod-lite-status           # Check instance health
make prod-lite-deploy           # Fast deploy (~30s)
make prod-lite-shell            # SSM session to instance

# Or use deploy-manager
deploy-manager lite status
deploy-manager lite deploy
deploy-manager lite shell
```

## Prod-Lite Details

### How It Works

1. **ASG launches spot instance** → Lambda updates Route53 A records
2. **User data script** bootstraps: clone repos, build frontend, setup venv, certbot, systemd
3. **Deploys are fast**: `git pull` + `pip install` + `migrate` + `systemctl restart`

### SSL Certificates (Let's Encrypt)

- Certbot obtains certificates for all domains on first boot
- Auto-renews via systemd timer every 60-90 days
- All domains share one certificate stored at `/etc/letsencrypt/live/api.eventzombie.com/`

### Connecting via SSM (No SSH Keys Needed)

```bash
# Get instance ID
INSTANCE_ID=$(aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Name,Values=superschedules-prod-lite" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

# Connect
aws ssm start-session --target $INSTANCE_ID --region us-east-1
```

### Log Locations

- CloudWatch: `/aws/superschedules/prod-lite/app`
  - Streams: `gunicorn-access`, `gunicorn-error`, `celery-worker`, `celery-beat`, `nginx-access`, `nginx-error`
- On instance: `/var/log/superschedules/`

### Manual Service Management

```bash
# On the instance via SSM
sudo systemctl status gunicorn celery-worker celery-beat nginx
sudo systemctl restart gunicorn
sudo journalctl -u gunicorn -f
```

## Debugging Production Issues

### 1. Check Instance and Target Health

```bash
# List running instances
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*superschedules*" "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],InstanceType,State.Name,LaunchTime]' \
  --output table --region us-east-1

# Check target group health (blue)
aws elbv2 describe-target-health \
  --target-group-arn "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-django-blue/176ef561d6a1f44e" \
  --region us-east-1

# Check target group health (green)
aws elbv2 describe-target-health \
  --target-group-arn "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-django-green/5495f976c4aab5ca" \
  --region us-east-1
```

### 2. CloudWatch Logs

**Prod log group:** `/aws/superschedules/prod/app`
**Prod-lite log group:** `/aws/superschedules/prod-lite/app`

```bash
# Tail prod-lite logs
aws logs tail /aws/superschedules/prod-lite/app --follow --region us-east-1

# Get recent Django logs (prod)
aws logs get-log-events \
  --log-group-name "/aws/superschedules/prod/app" \
  --log-stream-name "django" \
  --limit 50 --region us-east-1 \
  --query 'events[*].message' --output text | tr '\t' '\n'
```

### 3. SSM Session Manager

```bash
# Check SSM-managed instances
aws ssm describe-instance-information --region us-east-1 --output table

# Connect to prod-lite
deploy-manager lite shell
```

## Key Files

```
terraform/prod/                    # Docker + ALB environment
├── compute.tf                     # EC2 instances, ASG, launch templates
├── celery_beat.tf                 # Celery beat instance
├── iam.tf                         # IAM roles and policies
├── rds.tf                         # PostgreSQL (deletion_protection=true)
├── templates/user_data.sh.tftpl   # Docker bootstrap script

terraform/prod-lite/               # Non-Docker fast-deploy environment
├── compute.tf                     # Launch template + ASG (spot)
├── dns_lambda.tf                  # Lambda to update Route53
├── iam.tf                         # IAM roles (SSM, Secrets, S3, SQS, Bedrock)
├── security_group.tf              # HTTP/HTTPS, RDS access
├── lambda/dns_updater.py          # Route53 update function
├── templates/user_data_prod_lite.sh.tftpl  # Systemd bootstrap script

deploy_manager/deploy_manager/
├── cli.py                         # CLI commands (including `lite` subcommands)
├── interactive.py                 # Interactive dashboard
└── aws_client.py                  # AWS API wrapper

scripts/
└── deploy-prod-lite.sh            # Standalone SSM deploy script
```

## Common Issues and Solutions

### Worker Timeout / OOM

**Symptoms:**
```
[CRITICAL] WORKER TIMEOUT (pid:7)
[ERROR] Worker (pid:8) was sent SIGKILL! Perhaps out of memory?
```

**Solutions:**
- Reduce gunicorn worker count
- Upgrade instance type (prod-lite uses t3.medium with 4GB)
- Add swap file (both environments create swap automatically)

### Let's Encrypt Certificate Issues (Prod-Lite)

**Symptoms:** HTTPS not working after instance launch

**Check:**
```bash
# On instance via SSM
sudo certbot certificates
sudo nginx -t
sudo journalctl -u nginx
```

**Common causes:**
- DNS not propagated yet (Lambda updates Route53, wait 60-90s)
- Rate limits (max ~50 certs per domain per week)

### RDS Connection Issues

Both prod and prod-lite connect to the same RDS instance. Security group rules allow both:
- `superschedules-prod-app-sg` → RDS
- `superschedules-prod-lite-sg` → RDS

## Development Guidelines

- **Line length**: 120 characters maximum
- **Commit style**: Conventional Commits (feat:, fix:, chore:, etc.)
- **Testing**: Run `terraform plan` before applying changes
- **RDS Safety**: `deletion_protection = true` prevents accidental deletion
