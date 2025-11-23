"""AWS client wrapper for blue/green deployment operations."""
import boto3
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dateutil.parser import parse as parse_date


class AWSClient:
    """Wrapper for AWS API operations."""

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.ec2 = boto3.client("ec2", region_name=region)
        self.elbv2 = boto3.client("elbv2", region_name=region)
        self.autoscaling = boto3.client("autoscaling", region_name=region)
        self.pricing = boto3.client("pricing", region_name="us-east-1")  # Pricing API only in us-east-1

    def get_asg_info(self, asg_name: str) -> Optional[Dict]:
        """Get Auto Scaling Group information."""
        response = self.autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        if not response["AutoScalingGroups"]:
            return None
        return response["AutoScalingGroups"][0]

    def get_target_group_health(self, target_group_arn: str) -> List[Dict]:
        """Get target group health information."""
        response = self.elbv2.describe_target_health(
            TargetGroupArn=target_group_arn
        )
        return response["TargetHealthDescriptions"]

    def get_instance_details(self, instance_ids: List[str]) -> List[Dict]:
        """Get EC2 instance details."""
        if not instance_ids:
            return []
        response = self.ec2.describe_instances(InstanceIds=instance_ids)
        instances = []
        for reservation in response["Reservations"]:
            instances.extend(reservation["Instances"])
        return instances

    def get_spot_price(self, instance_type: str, availability_zone: str) -> Optional[float]:
        """Get current spot price for instance type."""
        response = self.ec2.describe_spot_price_history(
            InstanceTypes=[instance_type],
            ProductDescriptions=["Linux/UNIX"],
            AvailabilityZone=availability_zone,
            MaxResults=1
        )
        if response["SpotPriceHistory"]:
            return float(response["SpotPriceHistory"][0]["SpotPrice"])
        return None

    def check_spot_interruption(self, instance_id: str) -> Optional[Dict]:
        """Check if instance has spot interruption notice (requires SSM access)."""
        # This would require SSM access to the instance to check metadata
        # For now, we'll return None - can be enhanced later
        return None

    def calculate_instance_uptime(self, launch_time: datetime) -> Tuple[int, int, int]:
        """Calculate instance uptime in days, hours, minutes."""
        now = datetime.now(timezone.utc)
        delta = now - launch_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return days, hours, minutes

    def get_environment_status(self, asg_name: str, target_group_arns: Dict[str, str]) -> Dict:
        """Get comprehensive environment status."""
        asg_info = self.get_asg_info(asg_name)
        if not asg_info:
            return {
                "exists": False,
                "instances": [],
                "desired_capacity": 0,
                "health": {}
            }

        # Get instance details
        instance_ids = [i["InstanceId"] for i in asg_info.get("Instances", [])]
        instances = self.get_instance_details(instance_ids)

        # Get target group health
        health = {}
        for tg_name, tg_arn in target_group_arns.items():
            tg_health = self.get_target_group_health(tg_arn)
            health[tg_name] = tg_health

        # Calculate costs and uptime
        instance_details = []
        total_hourly_cost = 0.0

        for instance in instances:
            instance_type = instance["InstanceType"]
            lifecycle = instance.get("InstanceLifecycle", "on-demand")
            launch_time = instance["LaunchTime"]
            az = instance["Placement"]["AvailabilityZone"]

            # Get pricing
            if lifecycle == "spot":
                spot_price = self.get_spot_price(instance_type, az)
                hourly_cost = spot_price if spot_price else 0.0
            else:
                hourly_cost = 0.0094  # t3.micro on-demand hourly price

            total_hourly_cost += hourly_cost

            days, hours, minutes = self.calculate_instance_uptime(launch_time)

            instance_details.append({
                "instance_id": instance["InstanceId"],
                "instance_type": instance_type,
                "lifecycle": lifecycle,
                "state": instance["State"]["Name"],
                "launch_time": launch_time,
                "uptime": {"days": days, "hours": hours, "minutes": minutes},
                "hourly_cost": hourly_cost,
                "availability_zone": az
            })

        return {
            "exists": True,
            "asg_name": asg_name,
            "desired_capacity": asg_info["DesiredCapacity"],
            "min_size": asg_info["MinSize"],
            "max_size": asg_info["MaxSize"],
            "instances": instance_details,
            "health": health,
            "total_hourly_cost": total_hourly_cost,
            "total_monthly_cost": total_hourly_cost * 730  # Approximate month hours
        }
