"""Pytest configuration and shared fixtures."""
import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_console():
    """Mock rich console for testing output."""
    return Mock()


@pytest.fixture
def sample_instance_data():
    """Sample EC2 instance data for testing."""
    from datetime import datetime, timezone
    return {
        "InstanceId": "i-1234567890abcdef",
        "InstanceType": "t3.micro",
        "State": {"Name": "running"},
        "LaunchTime": datetime.now(timezone.utc),
        "Placement": {"AvailabilityZone": "us-east-1a"},
        "InstanceLifecycle": "spot"
    }


@pytest.fixture
def sample_asg_data():
    """Sample ASG data for testing."""
    return {
        "AutoScalingGroupName": "test-asg-blue",
        "DesiredCapacity": 1,
        "MinSize": 1,
        "MaxSize": 2,
        "Instances": [
            {
                "InstanceId": "i-1234567890abcdef",
                "LifecycleState": "InService",
                "HealthStatus": "Healthy"
            }
        ]
    }


@pytest.fixture
def sample_target_group_health():
    """Sample target group health data for testing."""
    return [
        {
            "Target": {"Id": "i-1234567890abcdef", "Port": 80},
            "TargetHealth": {
                "State": "healthy",
                "Reason": "Target.ResponseCodeMismatch",
                "Description": "Health checks passed"
            }
        }
    ]
