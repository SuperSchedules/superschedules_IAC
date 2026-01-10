# Deploy Manager: Add Prod-Lite Support

## Context

We have a `deploy_manager` CLI tool that currently manages the Docker-based prod environment. We've added a new `prod-lite` environment that runs without Docker (gunicorn/celery via systemd on a single spot instance).

The deploy_manager is located at `deploy_manager/deploy_manager/` and has:
- `cli.py` - Main CLI commands
- `interactive.py` - Interactive TUI dashboard
- `aws_client.py` - AWS API wrapper
- `deploy_state.py` - State management
- `ecr_client.py` - ECR operations

## Current Prod-Lite Deploy Process

Manually via SSM:
```bash
aws ssm start-session --target <INSTANCE_ID> --region us-east-1
sudo /opt/superschedules/scripts/deploy.sh
```

The deploy script on the instance does:
1. `git fetch && git reset --hard origin/main` (backend)
2. `pip install -r requirements-prod.txt`
3. `python manage.py migrate && collectstatic`
4. `systemctl restart gunicorn celery-worker celery-beat`
5. Same for frontend (git pull, pnpm install, pnpm build)

## Requirements

### 1. Add `lite` subcommand group
```bash
deploy-manager lite status    # Show instance status, services, logs
deploy-manager lite deploy    # Run deploy script via SSM
deploy-manager lite shell     # Open SSM session
deploy-manager lite logs      # Tail CloudWatch logs
deploy-manager lite restart   # Restart services without deploy
```

### 2. Implementation Details

**lite status** should show:
- Instance ID, IP, state, launch time
- Service status (gunicorn, celery-worker, celery-beat, nginx)
- Recent log snippets
- DNS resolution check

**lite deploy** should:
- Find the running prod-lite instance by tag `Name=superschedules-prod-lite`
- Run the deploy script via SSM `send-command`
- Stream/poll output until complete
- Show success/failure

**lite shell** should:
- Open interactive SSM session (may need to shell out to `aws ssm start-session`)

**lite logs** should:
- Tail CloudWatch log group `/aws/superschedules/prod-lite/app`
- Support filtering by stream (gunicorn-access, gunicorn-error, celery-worker, etc.)

**lite restart** should:
- Just restart services without git pull/build

### 3. Interactive Dashboard Updates

The interactive TUI (`interactive.py`) could show a prod-lite panel with:
- Instance status
- Quick deploy button
- Service status indicators
- Log viewer

### 4. Helper Functions Needed

```python
def get_prod_lite_instance():
    """Get running prod-lite instance by tag"""

def run_ssm_command(instance_id: str, commands: list[str]) -> dict:
    """Run commands via SSM and return output"""

def get_service_status(instance_id: str) -> dict:
    """Get systemd service status via SSM"""
```

## AWS Permissions Note

The local IAM user may need additional permissions:
- `ssm:SendCommand`
- `ssm:GetCommandInvocation`
- `logs:FilterLogEvents`
- `lambda:InvokeFunction` (optional, for DNS updates)

## Existing Code Reference

Look at `cli.py` for how prod commands are structured. The `lite` commands should follow the same patterns but use SSM instead of ECS/Docker operations.

## Testing

After implementation:
```bash
deploy-manager lite status
deploy-manager lite deploy
```
