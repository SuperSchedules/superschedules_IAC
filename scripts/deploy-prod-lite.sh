#!/usr/bin/env bash
# SSM-based deployment script for prod-lite
# Usage: ./deploy-prod-lite.sh [backend|frontend|all|status|shell]

set -euo pipefail

# Configuration
INSTANCE_NAME="superschedules-prod-lite"
REGION="us-east-1"
DEPLOY_TYPE="${1:-all}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $*"; }
error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $*"; exit 1; }
info() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*"; }

# Get instance ID from AWS
get_instance_id() {
    aws ec2 describe-instances \
        --region "$REGION" \
        --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].InstanceId' \
        --output text 2>/dev/null
}

# Get instance public IP
get_instance_ip() {
    aws ec2 describe-instances \
        --region "$REGION" \
        --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text 2>/dev/null
}

# Check if instance is SSM-managed
check_ssm() {
    local instance_id=$1
    local status
    status=$(aws ssm describe-instance-information \
        --region "$REGION" \
        --filters "Key=InstanceIds,Values=$instance_id" \
        --query 'InstanceInformationList[0].PingStatus' \
        --output text 2>/dev/null)

    if [ "$status" != "Online" ]; then
        error "Instance is not SSM-managed or not online yet.\nWait a few minutes for the instance to register with SSM."
    fi
}

# Run command via SSM
ssm_run() {
    local instance_id=$1
    local command=$2
    local timeout="${3:-300}"

    # Send command
    local command_id
    command_id=$(aws ssm send-command \
        --region "$REGION" \
        --instance-ids "$instance_id" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"$command\"]" \
        --timeout-seconds "$timeout" \
        --query 'Command.CommandId' \
        --output text)

    # Wait for command to complete
    aws ssm wait command-executed \
        --region "$REGION" \
        --command-id "$command_id" \
        --instance-id "$instance_id" 2>/dev/null || true

    # Get output
    aws ssm get-command-invocation \
        --region "$REGION" \
        --command-id "$command_id" \
        --instance-id "$instance_id" \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null

    # Check for errors
    local status
    status=$(aws ssm get-command-invocation \
        --region "$REGION" \
        --command-id "$command_id" \
        --instance-id "$instance_id" \
        --query 'Status' \
        --output text 2>/dev/null)

    if [ "$status" = "Failed" ]; then
        warn "Command failed. Error output:"
        aws ssm get-command-invocation \
            --region "$REGION" \
            --command-id "$command_id" \
            --instance-id "$instance_id" \
            --query 'StandardErrorContent' \
            --output text 2>/dev/null
        return 1
    fi
}

# Deploy backend
deploy_backend() {
    local instance_id=$1
    log "Deploying backend..."

    ssm_run "$instance_id" 'cd /opt/superschedules && \
        sudo -u www-data git fetch origin && \
        sudo -u www-data git reset --hard origin/main && \
        sudo -u www-data /opt/superschedules/venv/bin/pip install -r requirements-prod.txt -q && \
        sudo -u www-data /opt/superschedules/venv/bin/python manage.py migrate --noinput && \
        sudo -u www-data /opt/superschedules/venv/bin/python manage.py collectstatic --noinput -v0 && \
        sudo systemctl restart gunicorn celery-worker celery-beat && \
        echo "Backend deploy complete"' 600
}

# Deploy frontend
deploy_frontend() {
    local instance_id=$1
    log "Deploying frontend..."

    ssm_run "$instance_id" 'cd /opt/superschedules_frontend && \
        sudo -u www-data git fetch origin && \
        sudo -u www-data git reset --hard origin/main && \
        sudo -u www-data pnpm install --frozen-lockfile 2>/dev/null || sudo -u www-data pnpm install && \
        sudo -u www-data pnpm build && \
        echo "Frontend deploy complete"' 600
}

# Health check
health_check() {
    local instance_id=$1
    log "Running health checks..."

    info "Checking services..."
    ssm_run "$instance_id" 'for svc in gunicorn celery-worker celery-beat nginx; do \
        status=$(systemctl is-active $svc 2>/dev/null || echo "inactive"); \
        if [ "$status" = "active" ]; then \
            echo "  ✓ $svc"; \
        else \
            echo "  ✗ $svc ($status)"; \
        fi; \
    done' 30

    # HTTP health check from outside
    info "Checking API endpoint..."
    local api_domain="api.eventzombie.com"
    if curl -sf "https://$api_domain/api/live" -o /dev/null 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} API responding at https://$api_domain"
    else
        echo -e "  ${YELLOW}?${NC} API not responding yet (may still be starting)"
    fi
}

# Show status
show_status() {
    local instance_id=$1
    local ip=$2

    echo ""
    log "Instance Status"
    echo "  ID: $instance_id"
    echo "  IP: $ip"
    echo ""
    echo "Connect via SSM:"
    echo "  aws ssm start-session --target $instance_id --region $REGION"
    echo ""
    echo "URLs:"
    echo "  API:      https://api.eventzombie.com"
    echo "  Frontend: https://www.eventzombie.com"
    echo "  Admin:    https://admin.eventzombie.com"
}

# Interactive shell
start_shell() {
    local instance_id=$1
    log "Starting SSM session..."
    exec aws ssm start-session --target "$instance_id" --region "$REGION"
}

# Main
main() {
    echo ""
    log "=== Prod-Lite Deployment (SSM) ==="
    info "Action: $DEPLOY_TYPE"
    echo ""

    # Get instance ID
    local instance_id
    instance_id=$(get_instance_id)

    if [ -z "$instance_id" ] || [ "$instance_id" = "None" ] || [ "$instance_id" = "null" ]; then
        error "Could not find running prod-lite instance.\nRun 'make prod-lite-apply' first."
    fi

    local ip
    ip=$(get_instance_ip)

    info "Instance: $instance_id ($ip)"
    echo ""

    # For shell command, skip SSM check and just connect
    if [ "$DEPLOY_TYPE" = "shell" ]; then
        start_shell "$instance_id"
        exit 0
    fi

    # Check SSM connectivity
    check_ssm "$instance_id"

    local start_time=$(date +%s)

    case "$DEPLOY_TYPE" in
        backend)
            deploy_backend "$instance_id"
            ;;
        frontend)
            deploy_frontend "$instance_id"
            ;;
        all)
            deploy_backend "$instance_id"
            echo ""
            deploy_frontend "$instance_id"
            ;;
        status)
            show_status "$instance_id" "$ip"
            health_check "$instance_id"
            exit 0
            ;;
        *)
            echo "Usage: $0 [backend|frontend|all|status|shell]"
            echo ""
            echo "Commands:"
            echo "  backend   - Deploy backend only (git pull, pip, migrate, restart)"
            echo "  frontend  - Deploy frontend only (git pull, pnpm, build)"
            echo "  all       - Deploy both backend and frontend"
            echo "  status    - Show instance status and health"
            echo "  shell     - Open interactive SSM session"
            exit 1
            ;;
    esac

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    health_check "$instance_id"

    echo ""
    log "=== Deployment Complete in ${duration}s ==="
    show_status "$instance_id" "$ip"
}

main
