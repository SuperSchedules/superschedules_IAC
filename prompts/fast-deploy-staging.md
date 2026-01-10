# Fast Dev Deploy Environment for Superschedules

## Context: Current Production Infrastructure

You are helping me redesign my deployment setup for **Superschedules**, a Django app on AWS.

### Current Production Architecture

```
AWS Account: 353130947195
Region: us-east-1

┌─────────────────────────────────────────────────────────────────────────┐
│                         Current Prod Infrastructure                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ALB (supersched-prod-alb)                                              │
│    ├── /api/* → Django Target Group (blue/green)                        │
│    └── /* → Frontend Target Group (blue/green)                          │
│                                                                          │
│  EC2 Instances                                                           │
│    ├── superschedules-prod-asg-{blue|green} (t2.small, 2GB RAM)         │
│    │     └── Docker: frontend (nginx) + django + celery-worker          │
│    └── superschedules-prod-celery-beat (t3.small)                       │
│          └── Docker: celery-beat + celery-worker                         │
│                                                                          │
│  RDS PostgreSQL (superschedules-prod)                                   │
│    └── pgvector extension enabled                                        │
│                                                                          │
│  ECR Repositories                                                        │
│    ├── superschedules-api (Django backend)                              │
│    └── superschedules-frontend (React/nginx)                            │
│                                                                          │
│  SQS Queues (Celery broker)                                             │
│    ├── superschedules-prod-default                                       │
│    ├── superschedules-prod-embeddings                                    │
│    ├── superschedules-prod-geocoding                                     │
│    └── superschedules-prod-scraping                                      │
│                                                                          │
│  Secrets Manager: prod/superschedules/secrets                           │
│    └── DB_PASSWORD, DJANGO_SECRET_KEY, EMAIL_HOST_*, TURNSTILE_*        │
│                                                                          │
│  CloudWatch Logs: /aws/superschedules/prod/app                          │
│    └── Streams: django, celery-worker, celery-beat, frontend            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Current Terraform Structure

```
superschedules_IAC/
├── terraform/prod/
│   ├── compute.tf           # EC2 instances, ASG, launch templates
│   ├── celery_beat.tf       # Celery beat instance
│   ├── iam.tf               # IAM roles (superschedules-prod-ec2-role)
│   ├── ecr.tf               # ECR repositories
│   ├── variables.tf         # Input variables
│   ├── locals.tf            # Local values
│   └── templates/
│       └── user_data.sh.tftpl  # Instance bootstrap (Docker, migrations, seeding)
│
├── deploy_manager/
│   └── deploy_manager/
│       ├── cli.py           # Deploy CLI commands
│       ├── interactive.py   # Interactive deployment (blue/green switching)
│       ├── deploy_state.py  # Deployment state management
│       └── ecr_client.py    # ECR client for image management
│
└── CLAUDE.md                # Infrastructure documentation
```

### Current Deploy Flow (The Problem)

1. Push code to GitHub
2. GitHub Actions builds Docker images (~6 minutes)
3. Images pushed to ECR
4. Run deploy_manager to trigger ASG instance refresh (~5 minutes)
5. **Total: ~11 minutes per code change**

### Known Issues with Current Setup

- **OOM on t2.small**: Loading sentence transformers (`all-MiniLM-L6-v2`) causes worker SIGKILL
- **Slow iteration**: 11 minutes is too long for active development
- **ALB cost**: ~$16-20/month for a no-user dev environment
- **Secrets in console output**: user_data.sh logs secrets (needs fixing regardless)

---

## New Goal: Fast Dev Environment

I want to create a **non-Docker "staging" environment** optimized for fast iteration that I can optionally point production DNS at.

### DNS Setup

- `api.superschedules.com` → backend API
- `admin.superschedules.com` → Django admin / staff UI
- `www.superschedules.com` → public frontend (React static files)

(Currently these point to the ALB. I want to be able to point them at the new fast-deploy stack instead.)

### Design Decisions (Already Made)

- **DNS approach**: Use Lambda to update Route53 on instance launch (free, no Elastic IP)
- **Frontend**: Serve React static files from nginx on the same instance (no separate container)
- **Celery**: Run celery-worker AND celery-beat on the same instance
- **Git auth**: Repos are public, no auth needed
- **Shared resources**: Reuse existing RDS, SQS queues, and Secrets Manager from prod

### Requirements for New Environment

1. **NOT use Docker** for the app (run Django/gunicorn directly on host)
2. **Use spot instances** to keep costs low
3. **Auto-replace** spot instances if reclaimed (like current ASG behavior)
4. **SSH access** to EC2 instances for debugging
5. **Prebaked AMI** with dependencies so spot replacements boot fast
6. **No ALB** - terminate TLS on the instance with nginx + Let's Encrypt
7. **Extremely fast deploy**: `git pull` → `pip install` → `migrate` → `restart` in **seconds**

### App Technical Details

The Django app requires:

```
Python 3.12
PostgreSQL client libs (libpq-dev)
Build tools for native extensions

Key Python packages:
- Django + gunicorn + uvicorn
- Celery with SQS transport (kombu[sqs])
- sentence-transformers (loads all-MiniLM-L6-v2 - ~500MB RAM)
- psycopg2
- boto3
- pgvector

Services to run on the single instance:
- gunicorn (Django ASGI via uvicorn workers) on port 8000
- celery worker (queues: default, embeddings, geocoding, scraping)
- celery beat (scheduler)
- nginx (reverse proxy + static files for React frontend + TLS termination)

Environment variables needed (from Secrets Manager):
- DATABASE_URL or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD
- DJANGO_SECRET_KEY
- DJANGO_SETTINGS_MODULE=config.settings.production
- AWS_REGION=us-east-1
- EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
- TURNSTILE_SECRET_KEY
- CELERY_BROKER_URL (SQS)
```

### Repo Structure

**Backend** (superschedules - public repo):
```
superschedules/
├── manage.py
├── requirements.txt
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   └── production.py
│   ├── asgi.py
│   ├── celery.py
│   └── urls.py
├── api/
├── events/
├── locations/
├── chat_service/
└── ...
```

**Frontend** (superschedules_frontend - public repo):
```
superschedules_frontend/
├── package.json
├── src/
├── public/
└── build/  # Production build output to serve via nginx
```

---

## What I Want You To Produce

### 1. High-Level Architecture

Describe a non-Docker staging environment that:
- Uses an Auto Scaling Group with spot instances and `desired_capacity = 1`
- Uses a Launch Template referencing a custom AMI
- Exposes ports 80/443 via Security Group (no ALB)
- Terminates TLS on the instance with nginx + certbot
- Uses Lambda to update Route53 A records when instance IP changes
- Supports api/admin/www subdomains all on one instance

**Compare two deployment approaches**:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **AMI per release** | Deploy to instance → create AMI → update Launch Template → cycle ASG | Consistent, fast boot | Slower deploy (~5 min for AMI), more AMIs to manage |
| **Git-based deploy** | Boot with base AMI + user-data clone; deploys are `git pull` + restart | Very fast deploy (~30s), simple | Slower cold boot, git pull on every spot replace |

Recommend which approach for my situation (no users, speed priority).

### 2. Terraform for Staging Stack

Create a new `terraform/staging/` directory with:

**launch_template.tf**:
- Placeholder AMI ID (I'll update after baking)
- Instance type: `t3.medium` (need 4GB RAM for sentence transformers)
- Spot instance configuration
- IAM instance profile with:
  - SSM access
  - Secrets Manager read (`prod/superschedules/secrets`)
  - SQS access (existing queues)
  - CloudWatch Logs write
- User data script reference

**asg.tf**:
- `desired_capacity = 1`, `min_size = 1`, `max_size = 1`
- Spot-only capacity
- Auto-replacement on spot reclaim
- Health check configuration

**security_group.tf**:
- Inbound: 80, 443 from `0.0.0.0/0`
- Inbound: 22 from my IP (variable)
- Outbound: all

**dns.tf**:
- Lambda function triggered by ASG lifecycle hook
- Updates Route53 A records for api/admin/www when instance launches
- References existing Route53 hosted zone

**variables.tf**:
- Reference existing VPC, subnets, Route53 zone from prod
- Variables for my SSH IP, domain names, AMI ID

### 3. Base AMI Strategy

Provide a **Packer template** or step-by-step commands to create a base AMI with:

```bash
# System packages
python3.12, python3.12-venv, python3.12-dev
build-essential, libpq-dev, libffi-dev
git, nginx, certbot, python3-certbot-nginx
awscli, jq, nodejs, npm (for frontend builds)

# Pre-created structure
/opt/superschedules/          # Backend app directory
/opt/superschedules/venv/     # Python virtualenv (empty or with deps pre-installed)
/opt/superschedules/.env      # Placeholder for secrets
/opt/superschedules_frontend/ # Frontend directory
/var/log/superschedules/      # Log directory

# Systemd unit files (disabled, enabled on first boot)
/etc/systemd/system/gunicorn.service
/etc/systemd/system/celery-worker.service
/etc/systemd/system/celery-beat.service

# Nginx config
/etc/nginx/sites-available/superschedules
```

### 4. User-Data / First-Boot Bootstrap

Write `templates/user_data_staging.sh.tftpl` that:

1. Fetches secrets from Secrets Manager → writes `/opt/superschedules/.env`
   **IMPORTANT**: Do NOT log secrets to console output
2. Clones backend repo into `/opt/superschedules`
3. Clones frontend repo into `/opt/superschedules_frontend`
4. Builds frontend (`npm install && npm run build`)
5. Creates/updates virtualenv and installs Python requirements
6. Runs `migrate` and `collectstatic`
7. Configures nginx with actual domain names
8. Runs certbot for TLS certificates
9. Enables and starts systemd services (gunicorn, celery-worker, celery-beat)

### 5. Systemd + Nginx Config

**gunicorn.service**:
```ini
[Unit]
Description=Superschedules Gunicorn
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/superschedules
EnvironmentFile=/opt/superschedules/.env
ExecStart=/opt/superschedules/venv/bin/gunicorn config.asgi:application \
    --bind 127.0.0.1:8000 \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 120
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Provide similar units for:
- `celery-worker.service` (queues: default, embeddings, geocoding, scraping)
- `celery-beat.service`

**nginx config** with server blocks for:
- `api.superschedules.com` → proxy to gunicorn:8000
- `admin.superschedules.com` → proxy to gunicorn:8000
- `www.superschedules.com` → serve `/opt/superschedules_frontend/build/` static files

Include certbot/Let's Encrypt integration.

### 6. Fast Deploy Script

Create `scripts/deploy-staging.sh` that I run from my laptop:

```bash
#!/bin/bash
# Usage: ./deploy-staging.sh [backend|frontend|all]

# Find the staging instance
INSTANCE_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Environment,Values=staging" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text --region us-east-1)

# Deploy backend
deploy_backend() {
  ssh ubuntu@$INSTANCE_IP << 'DEPLOY'
    set -e
    cd /opt/superschedules
    git fetch origin && git reset --hard origin/main
    source venv/bin/activate
    pip install -r requirements.txt -q
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    sudo systemctl restart gunicorn celery-worker celery-beat
DEPLOY
}

# Deploy frontend
deploy_frontend() {
  ssh ubuntu@$INSTANCE_IP << 'DEPLOY'
    set -e
    cd /opt/superschedules_frontend
    git fetch origin && git reset --hard origin/main
    npm install
    npm run build
    sudo systemctl reload nginx
DEPLOY
}

# Main
case "${1:-all}" in
  backend)  deploy_backend ;;
  frontend) deploy_frontend ;;
  all)      deploy_backend && deploy_frontend ;;
esac

echo "Deploy complete! https://api.superschedules.com/api/live"
```

### 7. Integration With Existing Deploy Manager

Extend `deploy_manager/` to support both environments:

```bash
# Existing Docker+ALB prod
./deploy.py status --env prod
./deploy.py plan --env prod
./deploy.py apply --env prod

# New non-Docker staging
./deploy.py status --env staging
./deploy.py deploy --env staging              # Fast git-based deploy
./deploy.py deploy --env staging --backend    # Backend only
./deploy.py deploy --env staging --frontend   # Frontend only
./deploy.py ssh --env staging                 # SSH into the instance
./deploy.py logs --env staging                # Tail CloudWatch logs
./deploy.py bake-ami --env staging            # Create AMI from running instance
```

Provide a Python skeleton that:
- Parses `--env` argument to select terraform directory
- For staging, implements the fast `deploy` command (SSH-based)
- Shows instance status, public IP, health
- Estimates monthly cost per environment

### 8. GitHub Actions for Fast Deploy

Create `.github/workflows/deploy-staging.yml` that on push to `main`:

1. Does NOT build Docker images
2. Uses AWS SSM `send-command` to trigger deploy on the instance
3. Completes in <1 minute

```yaml
name: Fast Deploy to Staging
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Deploy via SSM
        run: |
          INSTANCE_ID=$(aws ec2 describe-instances \
            --filters "Name=tag:Environment,Values=staging" "Name=instance-state-name,Values=running" \
            --query 'Reservations[0].Instances[0].InstanceId' --output text)
          aws ssm send-command \
            --instance-ids $INSTANCE_ID \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=["/opt/superschedules/scripts/deploy.sh"]'
```

---

## Summary of Deliverables

1. [ ] Architecture diagram and approach recommendation (AMI-per-release vs git-based)
2. [ ] `terraform/staging/` directory with all resources
3. [ ] Packer template or AMI creation steps
4. [ ] `templates/user_data_staging.sh.tftpl`
5. [ ] Systemd unit files (gunicorn, celery-worker, celery-beat)
6. [ ] Nginx configuration with TLS for api/admin/www
7. [ ] `scripts/deploy-staging.sh`
8. [ ] Deploy manager CLI updates for multi-env support
9. [ ] GitHub Actions workflow for fast deploy

---

## Expected Cost Comparison

| Component | Current Prod | New Staging |
|-----------|-------------|-------------|
| ALB | ~$18/mo | $0 |
| EC2 (t2.small x2 + t3.small) | ~$35/mo | ~$8/mo (t3.medium spot) |
| NAT Gateway | ? | $0 (public subnet) |
| **Total** | ~$53+/mo | ~$8/mo |

The staging environment should cost roughly **$8-10/month** while providing **30-second deploys** instead of 11 minutes.
