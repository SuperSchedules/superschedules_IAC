"""Tests for AWS client wrapper."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
from deploy_manager.aws_client import AWSClient


@pytest.fixture
def aws_client():
    """Create AWSClient with mocked boto3 clients."""
    client = AWSClient(region="us-east-1")
    client.ec2 = Mock()
    client.elbv2 = Mock()
    client.autoscaling = Mock()
    client.pricing = Mock()
    return client


class TestGetASGInfo:
    """Tests for get_asg_info method."""

    def test_get_asg_info_success(self, aws_client):
        """Test getting ASG info successfully."""
        aws_client.autoscaling.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": [{
                "AutoScalingGroupName": "test-asg",
                "DesiredCapacity": 2,
                "MinSize": 1,
                "MaxSize": 3,
                "Instances": []
            }]
        }

        result = aws_client.get_asg_info("test-asg")

        assert result is not None
        assert result["AutoScalingGroupName"] == "test-asg"
        assert result["DesiredCapacity"] == 2
        aws_client.autoscaling.describe_auto_scaling_groups.assert_called_once_with(
            AutoScalingGroupNames=["test-asg"]
        )

    def test_get_asg_info_not_found(self, aws_client):
        """Test getting ASG info when ASG doesn't exist."""
        aws_client.autoscaling.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": []
        }

        result = aws_client.get_asg_info("nonexistent-asg")

        assert result is None


class TestGetTargetGroupHealth:
    """Tests for get_target_group_health method."""

    def test_get_target_group_health(self, aws_client):
        """Test getting target group health."""
        aws_client.elbv2.describe_target_health.return_value = {
            "TargetHealthDescriptions": [
                {
                    "Target": {"Id": "i-123", "Port": 80},
                    "TargetHealth": {"State": "healthy"}
                },
                {
                    "Target": {"Id": "i-456", "Port": 80},
                    "TargetHealth": {"State": "unhealthy"}
                }
            ]
        }

        result = aws_client.get_target_group_health("arn:aws:elasticloadbalancing:...")

        assert len(result) == 2
        assert result[0]["TargetHealth"]["State"] == "healthy"
        assert result[1]["TargetHealth"]["State"] == "unhealthy"


class TestGetInstanceDetails:
    """Tests for get_instance_details method."""

    def test_get_instance_details_success(self, aws_client):
        """Test getting instance details."""
        aws_client.ec2.describe_instances.return_value = {
            "Reservations": [{
                "Instances": [
                    {
                        "InstanceId": "i-123",
                        "InstanceType": "t3.micro",
                        "State": {"Name": "running"},
                        "LaunchTime": datetime.now(timezone.utc),
                        "Placement": {"AvailabilityZone": "us-east-1a"}
                    }
                ]
            }]
        }

        result = aws_client.get_instance_details(["i-123"])

        assert len(result) == 1
        assert result[0]["InstanceId"] == "i-123"
        assert result[0]["InstanceType"] == "t3.micro"

    def test_get_instance_details_empty_list(self, aws_client):
        """Test getting instance details with empty list."""
        result = aws_client.get_instance_details([])

        assert result == []
        aws_client.ec2.describe_instances.assert_not_called()


class TestCalculateInstanceUptime:
    """Tests for calculate_instance_uptime method."""

    def test_calculate_uptime_days(self, aws_client):
        """Test uptime calculation for days."""
        launch_time = datetime.now(timezone.utc).replace(
            day=datetime.now(timezone.utc).day - 2,
            hour=datetime.now(timezone.utc).hour - 3,
            minute=datetime.now(timezone.utc).minute - 15
        )

        days, hours, minutes = aws_client.calculate_instance_uptime(launch_time)

        assert days == 2
        assert hours == 3
        assert 14 <= minutes <= 16  # Allow small timing variations

    def test_calculate_uptime_hours(self, aws_client):
        """Test uptime calculation for hours."""
        from datetime import timedelta
        launch_time = datetime.now(timezone.utc) - timedelta(hours=5, minutes=30)

        days, hours, minutes = aws_client.calculate_instance_uptime(launch_time)

        assert days == 0
        assert hours == 5
        assert 29 <= minutes <= 31


class TestGetEnvironmentStatus:
    """Tests for get_environment_status method."""

    def test_environment_not_exists(self, aws_client):
        """Test getting status when ASG doesn't exist."""
        aws_client.autoscaling.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": []
        }

        result = aws_client.get_environment_status("nonexistent-asg", {})

        assert result["exists"] is False
        assert result["desired_capacity"] == 0
        assert result["instances"] == []

    def test_environment_with_instances(self, aws_client):
        """Test getting status with running instances."""
        launch_time = datetime.now(timezone.utc)

        aws_client.autoscaling.describe_auto_scaling_groups.return_value = {
            "AutoScalingGroups": [{
                "DesiredCapacity": 1,
                "MinSize": 1,
                "MaxSize": 2,
                "Instances": [{"InstanceId": "i-123"}]
            }]
        }

        aws_client.ec2.describe_instances.return_value = {
            "Reservations": [{
                "Instances": [{
                    "InstanceId": "i-123",
                    "InstanceType": "t3.micro",
                    "InstanceLifecycle": "spot",
                    "State": {"Name": "running"},
                    "LaunchTime": launch_time,
                    "Placement": {"AvailabilityZone": "us-east-1a"}
                }]
            }]
        }

        aws_client.elbv2.describe_target_health.return_value = {
            "TargetHealthDescriptions": [{
                "Target": {"Id": "i-123"},
                "TargetHealth": {"State": "healthy"}
            }]
        }

        aws_client.ec2.describe_spot_price_history.return_value = {
            "SpotPriceHistory": [{"SpotPrice": "0.0033"}]
        }

        result = aws_client.get_environment_status(
            "test-asg",
            {"frontend": "arn:aws:elasticloadbalancing:..."}
        )

        assert result["exists"] is True
        assert result["desired_capacity"] == 1
        assert len(result["instances"]) == 1
        assert result["instances"][0]["instance_type"] == "t3.micro"
        assert result["instances"][0]["lifecycle"] == "spot"
        assert result["instances"][0]["hourly_cost"] == 0.0033
        assert result["total_hourly_cost"] > 0


class TestGetSpotPrice:
    """Tests for get_spot_price method."""

    def test_get_spot_price_success(self, aws_client):
        """Test getting spot price."""
        aws_client.ec2.describe_spot_price_history.return_value = {
            "SpotPriceHistory": [
                {"SpotPrice": "0.0031", "Timestamp": datetime.now(timezone.utc)}
            ]
        }

        price = aws_client.get_spot_price("t3.micro", "us-east-1a")

        assert price == 0.0031

    def test_get_spot_price_no_history(self, aws_client):
        """Test getting spot price with no history."""
        aws_client.ec2.describe_spot_price_history.return_value = {
            "SpotPriceHistory": []
        }

        price = aws_client.get_spot_price("t3.micro", "us-east-1a")

        assert price is None
