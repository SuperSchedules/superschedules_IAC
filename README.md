# Superschedules IAC

This repository contains Terraform configuration for the Superschedules project. The Terraform code lives under the `terraform/`
directory and is organized into environments for development (both EC2 and local) and production. The development configuration
installs required packages, clones several Git repositories via separate setup scripts, and can optionally provision an AWS EC2
instance for the dev environment.

## Usage

1. Ensure [Terraform](https://developer.hashicorp.com/terraform/install) is installed locally.
2. Ensure you have an SSH key configured with access to GitHub.
3. (Optional) Set `INSTALL_DOTFILES=true` to clone and install your dotfiles.
4. Choose one of the following targets:

```sh
# Provision a dev EC2 instance and run setup scripts
make dev-ec2

# Provision a dev EC2 instance and install dotfiles
make dev-ec2 INSTALL_DOTFILES=true

# Run setup scripts locally without creating an EC2 instance
make dev-local

# Run setup scripts locally and install dotfiles
make dev-local INSTALL_DOTFILES=true

# Provision/refresh the production environment (blue/green aware)
make prod-deploy

# Prepare a new green fleet at full capacity while keeping blue live
make deploy:new-green GREEN_CAPACITY=2

# Shift 10% of traffic to green for a canary
make deploy:canary-10

# Move to a 50/50 canary split
make deploy:canary-50

# Send 100% of traffic to green
make deploy:flip

# After monitoring, retire blue capacity (defaults to 3 minute drain)
make deploy:retire-blue DRAIN_WAIT=300

# Roll back to blue immediately
make deploy:rollback
```

The development configuration uses two resources:

- **setup_once** updates apt package information and installs base packages: `git`, `python3-pip`, `python3-venv`, `curl`, and `build-essential`. This runs only once unless the resource is tainted.
- **setup_environment** runs on every apply. It verifies that your SSH key can authenticate with GitHub and delegates repository setup to scripts in `scripts/`.

When run locally, the configuration also installs [Ollama](https://ollama.com) and pulls the `gemma2:latest` model.

The following setup scripts under `terraform/dev/scripts` clone or update repositories and perform per-project initialization:

- `setup_dotfiles.sh` for [dotfiles-1](https://github.com/gkirkpatrick/dotfiles-1).
- `setup_superschedules.sh` for [superschedules](https://github.com/gkirkpatrick/superschedules) and its Python virtual environment.
- `setup_superschedules_IAC.sh` for [superschedules_IAC](https://github.com/gkirkpatrick/superschedules_IAC).
- `setup_superschedules_frontend.sh` for [superschedules_frontend](https://github.com/gkirkpatrick/superschedules_frontend), which runs a cross-platform bootstrap script to install Node.js 20, pin `pnpm`, and install dependencies without touching user shell configuration.
- `setup_superschedules_collector.sh` for [superschedules_collector](https://github.com/gkirkpatrick/superschedules_collector) and its Python virtual environment.
- `setup_superschedules_navigator.sh` for [superschedules_navigator](https://github.com/gkirkpatrick/superschedules_navigator) and its Python virtual environment.

## Production blue/green deployment

The production environment is managed through the reusable module in `modules/service_bluegreen`. It provisions paired blue/green target groups and Auto Scaling Groups that share a single launch template and ALB listener. The module wires listener weights, lifecycle hooks, and readiness outputs so that one Terraform apply (or the Make targets above) is all that is required to move traffic between fleets with zero downtime.

A minimal, self-contained example that wires the module to an existing ALB and launch template is included in `envs/prod/main.tf`.

### Ready-to-flip gating

The module exports `bluegreen_ready_to_flip` and `bluegreen_readiness` to gate production flips. Before changing weights, run:

```sh
terraform -chdir=terraform/prod apply -refresh-only
terraform -chdir=terraform/prod output bluegreen_readiness
terraform -chdir=terraform/prod output bluegreen_ready_to_flip
```

`ready_to_flip` will only become `true` after every instance in the standby color is `InService` and healthy according to the ALB `/ready` check. Keep `enable_instance_protection = true` during flips so that Auto Scaling does not scale the target color in while you are switching traffic.

### Lifecycle hook bootstrap

Each Auto Scaling Group has a launch lifecycle hook that pauses new instances until your bootstrap logic signals readiness. The following Systems Manager Run Command snippet installs dependencies and completes the hook only after the `/ready` endpoint succeeds:

```sh
aws ssm send-command \
  --document-name "AWS-RunShellScript" \
  --targets "Key=tag:aws:autoscaling:groupName,Values=superschedules-prod-asg-green" \
  --comment "Bootstrap and signal readiness" \
  --parameters '{"commands":[
    "#!/bin/bash",
    "set -euo pipefail",
    "# run bootstrap here",
    "/usr/bin/aws autoscaling complete-lifecycle-action --lifecycle-hook-name superschedules-prod-green-launch --auto-scaling-group-name superschedules-prod-asg-green --lifecycle-action-token $LIFECYCLE_ACTION_TOKEN --lifecycle-action-result CONTINUE"
  ]}'
```

Replace the comment section with your actual provisioning commands. Use `ABANDON` instead of `CONTINUE` if bootstrap fails so the instance is terminated automatically.

### Plan milestones

The table below documents the expected Terraform plan deltas for each deployment stage:

```text
# Initial blue-only deployment
# module.service_bluegreen.aws_autoscaling_group.this["green"] will be created
# module.service_bluegreen.aws_lb_target_group.this["green"] will be created

# Introduce green capacity (make deploy:new-green)
# module.service_bluegreen.aws_autoscaling_group.this["green"]: desired_capacity from 0 to N

# Canary 10/90 (make deploy:canary-10)
# module.service_bluegreen.aws_lb_listener.this[0] default action weights: blue=90, green=10

# Canary 50/50 (make deploy:canary-50)
# module.service_bluegreen.aws_lb_listener.this[0] default action weights: blue=50, green=50

# Full flip (make deploy:flip)
# module.service_bluegreen.aws_lb_listener.this[0] default action forwards 100% to green

# Retire blue (make deploy:retire-blue)
# module.service_bluegreen.aws_autoscaling_group.this["blue"] desired_capacity from current to 0
```

Run `terraform -chdir=terraform/prod plan` with the appropriate `-var` overrides from the Make targets to see the complete diff before each stage.

### Rollback

To roll back, run `make deploy:rollback`. This sends 100% of traffic back to blue while keeping the green ASG online so you can investigate. If you also want to scale green down, follow with `make deploy:new-green GREEN_CAPACITY=0`.

### Migration guide

1. Import existing single-color resources into state:
   ```sh
   terraform -chdir=terraform/prod import module.service_bluegreen.aws_lb_listener.this[0] <listener-arn>
   terraform -chdir=terraform/prod import module.service_bluegreen.aws_lb_target_group.this["blue"] <existing-tg-arn>
   terraform -chdir=terraform/prod import module.service_bluegreen.aws_autoscaling_group.this["blue"] <existing-asg-name>
   ```
2. Apply with `green_desired_capacity = 0` so the new resources (green ASG/TG) are created alongside the live blue stack.
3. Run `make deploy:new-green` to spin up green instances on the new target group.
4. Walk through the canary and flip commands above.

If importing the listener is not desirable, set `listener_arn = null` and Terraform will create a fresh listener that can be promoted once traffic is off the legacy resources.

When `listener_arn` is supplied the module installs an all-path (`/*`) listener rule instead of modifying the default action so the pre-existing listener is never replaced. Ensure there are no higher-priority rules that would override this catch-all route.

## Docker and CI/CD

Each service has Docker support for containerized deployment:

### Local Development with Docker

**Backend (Django + FastAPI)**:
```bash
cd ~/superschedules
docker build -t superschedules-api .
docker run -p 8000:8000 --net host --user $(id -u):$(id -g) \
  -v ~/.cache:/home/$(whoami)/.cache \
  -v /var/run/postgresql:/var/run/postgresql \
  superschedules-api
```

**Collector Service**:
```bash
cd ~/superschedules_collector  
docker build -t superschedules-collector .
docker run -p 8001:8001 superschedules-collector
```

**Navigator Service**:
```bash
cd ~/superschedules_navigator
docker build -t superschedules-navigator .
docker run -p 8004:8004 superschedules-navigator
```

**Frontend**:
```bash
cd ~/superschedules_frontend
docker build -t superschedules-frontend .
docker run -p 3000:80 superschedules-frontend
```

### AWS ECR and CI/CD

1. **Create ECR repositories**:
```bash
./scripts/create-ecr-repos.sh
```

2. **Configure GitHub secrets**:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY` 
- `AWS_ACCOUNT_ID`

3. **Automatic builds**: GitHub Actions workflow automatically builds and pushes Docker images to ECR on push to `main`/`develop` branches.

### Service Ports

- **Backend**: 8000 (Django + FastAPI)
- **Collector**: 8001 (FastAPI)
- **Navigator**: 8004 (FastAPI)  
- **Frontend**: 3000 (nginx)

All services expose health endpoints at `/health`, `/live`, and `/ready`. The blue/green module routes traffic only after `/ready` succeeds.
