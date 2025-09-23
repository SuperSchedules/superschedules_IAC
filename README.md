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

# Provision the production EC2 instance
make prod-deploy
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

An `aws_instance` resource named `dev` and a similar `prod` instance have been added as starting points for hosting the environments on AWS. Provide the `ssh_key_name` variable to supply your existing key pair.

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

All services expose health endpoints at `/health`, `/live`, and `/ready`.
