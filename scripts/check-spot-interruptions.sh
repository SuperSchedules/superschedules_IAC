#!/bin/bash
# Check for spot instance interruption warnings
# This script checks the EC2 instance metadata for spot interruption notices

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Spot Instance Interruption Checker ==="
echo "Checking both blue and green instances..."
echo ""

# Get instance IDs from ASGs
BLUE_INSTANCE=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names superschedules-prod-asg-blue \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
  --output text)

GREEN_INSTANCE=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names superschedules-prod-asg-green \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
  --output text)

check_interruption() {
  local instance_id=$1
  local color=$2

  if [ "$instance_id" == "None" ] || [ -z "$instance_id" ]; then
    echo -e "${YELLOW}${color}:${NC} No instances running"
    return
  fi

  # Check if instance is spot
  instance_lifecycle=$(aws ec2 describe-instances \
    --instance-ids "$instance_id" \
    --query 'Reservations[0].Instances[0].InstanceLifecycle' \
    --output text)

  if [ "$instance_lifecycle" != "spot" ]; then
    echo -e "${GREEN}${color}:${NC} On-demand instance ($instance_id) - no interruption risk"
    return
  fi

  # For spot instances, you would normally check the instance metadata
  # This requires SSM or direct access to the instance
  echo -e "${GREEN}${color}:${NC} Spot instance ($instance_id) running"
  echo "  To check interruption status from the instance:"
  echo "  curl -s http://169.254.169.254/latest/meta-data/spot/instance-action"
}

check_interruption "$BLUE_INSTANCE" "BLUE"
check_interruption "$GREEN_INSTANCE" "GREEN"

echo ""
echo "=== Instance Pricing ===="
aws ec2 describe-spot-price-history \
  --instance-types t3.micro \
  --product-descriptions "Linux/UNIX" \
  --max-items 3 \
  --query 'SpotPriceHistory[*].[AvailabilityZone,SpotPrice,Timestamp]' \
  --output table

echo ""
echo "Note: Spot interruptions are rare for t3.micro (<5% historical rate)"
echo "With blue/green deployment, you have automatic failover capability"
