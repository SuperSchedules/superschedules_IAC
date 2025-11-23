# Superschedules Blue/Green Deployment Manager

A Python CLI tool for managing blue/green deployments on AWS with spot instance support.

## Features

- **Status Dashboard**: Real-time view of both blue and green environments including:
  - Instance details (ID, type, lifecycle, state, uptime)
  - Health check status for all target groups
  - Cost breakdown (hourly, daily, monthly estimates)
  - Active environment indicator

- **Automated Deployments**: Deploy to the inactive environment with:
  - Automatic detection of inactive environment
  - Real-time progress monitoring
  - Health check validation
  - Interactive traffic flip prompt

- **Traffic Management**: Seamlessly flip traffic between environments

- **Spot Instance Aware**: Displays lifecycle type and optimized pricing

## Installation

1. Create and activate the virtual environment:

```bash
cd deploy_manager
python3 -m venv venv
source venv/bin/activate
```

2. Install the package:

```bash
pip install -e .
```

3. Alternatively, use directly from the venv:

```bash
deploy_manager/venv/bin/deploy-manager --help
```

## Usage

### Interactive Dashboard (NEW! ⭐)

Run the interactive dashboard with live-updating status and menu:

```bash
deploy-manager dashboard
```

Features:
- **Auto-refreshing status** every 5 seconds
- **Live cost tracking** for both environments
- **Interactive menu** with keyboard navigation:
  - `1` - Deploy to Inactive Environment
  - `2` - Flip Traffic
  - `3` - Scale Down Inactive Environment
  - `4` - Refresh Status
  - `5` - Exit
  - `q` - Quick exit
  - Arrow keys or Enter to navigate menu

The dashboard provides a real-time view of:
- Active environment indicator (⭐)
- All instances with lifecycle type (Spot/On-Demand)
- Health checks for all target groups
- Live uptime counters
- Cost breakdowns (hourly, daily, monthly)

### Check Deployment Status

View comprehensive status of both blue and green environments:

```bash
deploy-manager status
```

This displays:
- Which environment is currently active (receiving traffic)
- Instance details for each environment
- Health status of all target groups
- Cost estimates (hourly, daily, monthly)
- Instance uptime

### Deploy New Version

Deploy a new version to the inactive environment:

```bash
deploy-manager deploy
```

This will:
1. Detect which environment is currently active
2. Deploy to the inactive environment
3. Monitor deployment progress in real-time
4. Validate health checks
5. Prompt you to flip traffic when ready

The command automatically:
- Runs `make deploy:new-green` or `make deploy:new-blue`
- Monitors Auto Scaling Group status
- Checks target group health
- Waits for all instances to be healthy

### Flip Traffic

Manually flip traffic between environments:

```bash
deploy-manager flip
```

Or flip to a specific environment:

```bash
deploy-manager flip --to green
deploy-manager flip --to blue
```

This runs the `make flip` command with safety prompts.

## Example Workflow

1. **Check current status**:
   ```bash
   deploy-manager status
   ```
   Output shows Blue is active with 1 instance running

2. **Deploy new version to inactive environment (Green)**:
   ```bash
   deploy-manager deploy
   ```
   - Confirms you want to deploy to Green
   - Shows terraform output
   - Monitors until Green is healthy
   - Prompts: "Do you want to flip traffic to the new environment now?"

3. **Flip traffic** (if not done in step 2):
   ```bash
   deploy-manager flip
   ```
   - Confirms the traffic flip
   - Runs `make flip`
   - Traffic now goes to Green

4. **Verify with status**:
   ```bash
   deploy-manager status
   ```
   Output now shows Green is active

5. **Scale down old environment** (optional):
   ```bash
   make deploy:scale-down-blue
   ```

## Configuration

Configuration is in `deploy_manager/config.py`:

- AWS region
- ASG names for blue and green
- Target group ARNs

Update these values if your infrastructure naming differs.

## Requirements

- Python 3.8+
- AWS credentials configured (via AWS CLI, environment variables, or IAM role)
- Terraform infrastructure deployed
- Existing Makefile with deployment targets

## Architecture

The tool consists of:

- `cli.py`: Click-based command-line interface with Rich formatting
- `aws_client.py`: Boto3 wrapper for AWS API calls
- `config.py`: Configuration for ASG names and target groups

## Cost Tracking

The tool automatically calculates costs based on:
- **Spot instances**: Real-time spot price from AWS API
- **On-demand instances**: Standard t3.micro pricing ($0.0094/hr)

Monthly estimates assume 730 hours (average month length).

## Troubleshooting

**"No module named 'deploy_manager'"**
- Make sure you're in the deploy_manager directory
- Activate the venv: `source venv/bin/activate`
- Reinstall: `pip install -e .`

**"Timeout waiting for environment to become healthy"**
- Check AWS console for EC2 instance issues
- Verify security groups allow health check traffic
- Check application logs in the instance
- May need to increase timeout (currently 10 minutes)

**"Cannot determine active environment"**
- Manually check: `terraform -chdir=terraform/prod output active_color`
- Verify listener configuration in AWS console

## Development

To modify the tool:

1. Edit files in `deploy_manager/deploy_manager/`
2. Changes take effect immediately (editable install)
3. Test with: `deploy-manager status`

## Future Enhancements

Potential improvements:
- Gradual traffic shifting (canary deployments)
- Spot interruption notifications via CloudWatch Events
- Automatic failover on spot interruption
- Rollback command
- Deployment history tracking
- Slack/email notifications
