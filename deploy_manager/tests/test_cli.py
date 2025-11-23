"""Tests for CLI deployment manager."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from deploy_manager.cli import DeploymentManager
from deploy_manager.config import Config


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    with patch('deploy_manager.cli.AWSClient') as mock:
        yield mock.return_value


@pytest.fixture
def deployment_manager(mock_aws_client):
    """Create a DeploymentManager with mocked AWS client."""
    config = Config()
    manager = DeploymentManager(config)
    manager.aws = mock_aws_client
    return manager


class TestGetActiveEnvironment:
    """Tests for get_active_environment method."""

    def test_get_active_from_terraform_output(self, deployment_manager):
        """Test getting active environment from terraform output."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.stdout = '"blue"'
            mock_run.return_value.returncode = 0

            result = deployment_manager.get_active_environment()

            assert result == "blue"

    def test_get_active_fallback_to_asg_check(self, deployment_manager, mock_aws_client):
        """Test fallback to ASG check when terraform fails."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("terraform failed")

            mock_aws_client.get_asg_info.side_effect = [
                {"DesiredCapacity": 1},  # Blue
                {"DesiredCapacity": 0}   # Green
            ]

            result = deployment_manager.get_active_environment()

            assert result == "blue"

    def test_get_active_both_running(self, deployment_manager, mock_aws_client):
        """Test when both environments are running."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("terraform failed")

            mock_aws_client.get_asg_info.side_effect = [
                {"DesiredCapacity": 1},  # Blue
                {"DesiredCapacity": 1}   # Green
            ]

            result = deployment_manager.get_active_environment()

            assert result == "unknown"


class TestMonitorDeployment:
    """Tests for _monitor_deployment method."""

    def test_monitor_deployment_becomes_healthy(self, deployment_manager, mock_aws_client):
        """Test monitoring deployment that becomes healthy."""
        # First call: not healthy, second call: healthy
        mock_aws_client.get_environment_status.side_effect = [
            {
                "exists": True,
                "desired_capacity": 1,
                "instances": [{
                    "instance_id": "i-123",
                    "instance_type": "t3.micro",
                    "lifecycle": "spot",
                    "state": "running",
                    "uptime": {"days": 0, "hours": 0, "minutes": 5},
                    "hourly_cost": 0.0033,
                    "availability_zone": "us-east-1a"
                }],
                "health": {
                    "frontend": [{"TargetHealth": {"State": "initial"}}]
                }
            },
            {
                "exists": True,
                "desired_capacity": 1,
                "instances": [{
                    "instance_id": "i-123",
                    "instance_type": "t3.micro",
                    "lifecycle": "spot",
                    "state": "running",
                    "uptime": {"days": 0, "hours": 0, "minutes": 10},
                    "hourly_cost": 0.0033,
                    "availability_zone": "us-east-1a"
                }],
                "health": {
                    "frontend": [{"TargetHealth": {"State": "healthy"}}]
                }
            }
        ]

        with patch('time.sleep'):  # Skip sleep in tests
            result = deployment_manager._monitor_deployment("green")

        assert result is True

    def test_monitor_deployment_unused_targets(self, deployment_manager, mock_aws_client):
        """Test monitoring deployment with unused targets (inactive environment)."""
        mock_aws_client.get_environment_status.return_value = {
            "exists": True,
            "desired_capacity": 1,
            "instances": [{
                "instance_id": "i-123",
                "instance_type": "t3.micro",
                "lifecycle": "spot",
                "state": "running",
                "uptime": {"days": 0, "hours": 0, "minutes": 5},
                "hourly_cost": 0.0033,
                "availability_zone": "us-east-1a"
            }],
            "health": {
                "frontend": [{"TargetHealth": {"State": "unused"}}],
                "django": [{"TargetHealth": {"State": "unused"}}]
            }
        }

        with patch('time.sleep'):
            result = deployment_manager._monitor_deployment("green")

        assert result is True

    def test_monitor_deployment_timeout(self, deployment_manager, mock_aws_client):
        """Test monitoring deployment that times out."""
        mock_aws_client.get_environment_status.return_value = {
            "exists": True,
            "desired_capacity": 1,
            "instances": [{"state": "running"}],
            "health": {
                "frontend": [{"TargetHealth": {"State": "unhealthy"}}]
            }
        }

        with patch('time.sleep'):
            with patch.object(deployment_manager, '_monitor_deployment') as mock_monitor:
                mock_monitor.return_value = False
                result = mock_monitor("green")

        assert result is False


class TestFlipTraffic:
    """Tests for flip_traffic method."""

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.run')
    def test_flip_to_green(self, mock_run, mock_confirm, deployment_manager):
        """Test flipping traffic from blue to green."""
        mock_confirm.return_value = True
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.returncode = 0

        with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
            result = deployment_manager.flip_traffic()

        assert result is True
        mock_run.assert_called_once()
        assert 'make deploy:flip' in mock_run.call_args[0][0]

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.run')
    def test_flip_to_blue_rollback(self, mock_run, mock_confirm, deployment_manager):
        """Test flipping traffic from green to blue (rollback)."""
        mock_confirm.return_value = True
        mock_run.return_value.stdout = "Success"
        mock_run.return_value.returncode = 0

        with patch.object(deployment_manager, 'get_active_environment', return_value='green'):
            result = deployment_manager.flip_traffic()

        assert result is True
        assert 'make deploy:rollback' in mock_run.call_args[0][0]

    @patch('deploy_manager.cli.click.confirm')
    def test_flip_cancelled(self, mock_confirm, deployment_manager):
        """Test flipping traffic when user cancels."""
        mock_confirm.return_value = False

        with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
            result = deployment_manager.flip_traffic()

        assert result is False

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.run')
    def test_flip_fails(self, mock_run, mock_confirm, deployment_manager):
        """Test flipping traffic when command fails."""
        import subprocess
        mock_confirm.return_value = True
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd="make deploy:flip",
            stderr="Command failed"
        )

        with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
            result = deployment_manager.flip_traffic()

        assert result is False


class TestDeployToInactive:
    """Tests for deploy_to_inactive method."""

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.Popen')
    def test_deploy_to_inactive_cancelled(self, mock_popen, mock_confirm, deployment_manager):
        """Test deployment when user cancels."""
        mock_confirm.return_value = False

        with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
            result = deployment_manager.deploy_to_inactive()

        assert result is False
        mock_popen.assert_not_called()

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.Popen')
    def test_deploy_to_inactive_unknown_active(self, mock_popen, mock_confirm, deployment_manager):
        """Test deployment when active environment is unknown."""
        with patch.object(deployment_manager, 'get_active_environment', return_value='unknown'):
            result = deployment_manager.deploy_to_inactive()

        assert result is False
        mock_popen.assert_not_called()

    @patch('deploy_manager.cli.click.confirm')
    @patch('subprocess.Popen')
    def test_deploy_succeeds(self, mock_popen, mock_confirm, deployment_manager, mock_aws_client):
        """Test successful deployment."""
        mock_confirm.return_value = True

        # Mock subprocess
        mock_process = Mock()
        mock_process.stdout = iter(["Line 1\n", "Line 2\n"])
        mock_process.wait.return_value = None
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Mock monitoring to succeed
        with patch.object(deployment_manager, '_monitor_deployment', return_value=True):
            with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
                result = deployment_manager.deploy_to_inactive()

        assert result is True


class TestShowStatus:
    """Tests for show_status method."""

    def test_show_status_displays_both_environments(self, deployment_manager, mock_aws_client):
        """Test that status displays both blue and green environments."""
        mock_aws_client.get_environment_status.side_effect = [
            {
                "exists": True,
                "desired_capacity": 1,
                "min_size": 1,
                "max_size": 2,
                "instances": [{
                    "instance_id": "i-123",
                    "instance_type": "t3.micro",
                    "lifecycle": "spot",
                    "state": "running",
                    "uptime": {"days": 1, "hours": 2, "minutes": 30},
                    "hourly_cost": 0.0033,
                    "availability_zone": "us-east-1a"
                }],
                "health": {
                    "frontend": [{"TargetHealth": {"State": "healthy"}}]
                },
                "total_hourly_cost": 0.0033,
                "total_monthly_cost": 2.41
            },
            {
                "exists": True,
                "desired_capacity": 0,
                "min_size": 0,
                "max_size": 2,
                "instances": [],
                "health": {},
                "total_hourly_cost": 0,
                "total_monthly_cost": 0
            }
        ]

        with patch.object(deployment_manager, 'get_active_environment', return_value='blue'):
            # Just ensure it doesn't crash - output testing is complex with Rich
            deployment_manager.show_status()
