"""Deployment state tracking via S3."""
import json
import os
import boto3
from typing import Dict, List, Optional
from datetime import datetime, timezone
from botocore.exceptions import ClientError


class DeployState:
    """Track deployment history in S3 for rollback support."""

    S3_BUCKET = "superschedules-data"
    S3_KEY = "deploy-state/history.json"
    MAX_HISTORY = 50  # Keep last 50 deployments

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.s3 = boto3.client("s3", region_name=region)

    def _load_state(self) -> Dict:
        """Load state from S3."""
        try:
            response = self.s3.get_object(Bucket=self.S3_BUCKET, Key=self.S3_KEY)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return {"deployments": []}
            raise

    def _save_state(self, state: Dict) -> None:
        """Save state to S3."""
        self.s3.put_object(
            Bucket=self.S3_BUCKET,
            Key=self.S3_KEY,
            Body=json.dumps(state, indent=2, default=str),
            ContentType="application/json"
        )

    def record_deploy(
        self,
        tag: str,
        service: str = "all",
        deployed_by: Optional[str] = None
    ) -> None:
        """
        Record a deployment to history.

        Args:
            tag: Image tag that was deployed (e.g., main-abc123...)
            service: Service name (api, frontend, all)
            deployed_by: Username who triggered the deploy
        """
        state = self._load_state()

        # Get username from environment if not provided
        if deployed_by is None:
            deployed_by = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

        deployment = {
            "tag": tag,
            "service": service,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deployed_by": deployed_by,
        }

        # Add to beginning of list
        state["deployments"].insert(0, deployment)

        # Trim to max history
        state["deployments"] = state["deployments"][:self.MAX_HISTORY]

        self._save_state(state)

    def get_history(self, limit: int = 10) -> List[Dict]:
        """
        Get deployment history.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of deployment records, newest first
        """
        state = self._load_state()
        return state["deployments"][:limit]

    def get_current_tag(self) -> Optional[str]:
        """Get the most recently deployed tag."""
        history = self.get_history(limit=1)
        if history:
            return history[0].get("tag")
        return None

    def get_previous_tag(self) -> Optional[str]:
        """Get the tag deployed before the current one (for rollback)."""
        history = self.get_history(limit=2)
        if len(history) >= 2:
            return history[1].get("tag")
        return None

    def get_tag_at_index(self, index: int) -> Optional[str]:
        """Get tag at specific history index (0 = current, 1 = previous, etc.)."""
        history = self.get_history(limit=index + 1)
        if len(history) > index:
            return history[index].get("tag")
        return None

    def find_tag_in_history(self, tag: str) -> Optional[Dict]:
        """Find a specific tag in deployment history."""
        state = self._load_state()
        for deployment in state["deployments"]:
            if deployment.get("tag") == tag:
                return deployment
        return None
