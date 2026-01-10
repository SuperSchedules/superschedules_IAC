"""ECR client for image management and polling."""
import time
import random
import boto3
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone
from botocore.exceptions import ClientError


class ECRClient:
    """Client for ECR operations including image polling."""

    # ECR repository names
    REPOS = {
        "api": "superschedules-api",
        "frontend": "superschedules-frontend",
        "navigator": "superschedules-navigator",
        "collector": "superschedules-collector",
    }

    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.ecr = boto3.client("ecr", region_name=region)

    def get_repo_name(self, service: str) -> str:
        """Get ECR repository name for a service."""
        return self.REPOS.get(service, service)

    def image_exists(self, repo: str, tag: str) -> bool:
        """Check if an image tag exists and has a digest."""
        try:
            response = self.ecr.describe_images(
                repositoryName=repo,
                imageIds=[{"imageTag": tag}]
            )
            # Check that we got a valid image with a digest
            images = response.get("imageDetails", [])
            return len(images) > 0 and images[0].get("imageDigest") is not None
        except ClientError as e:
            if e.response["Error"]["Code"] == "ImageNotFoundException":
                return False
            raise

    def get_image_info(self, repo: str, tag: str) -> Optional[Dict]:
        """Get detailed information about a specific image tag."""
        try:
            response = self.ecr.describe_images(
                repositoryName=repo,
                imageIds=[{"imageTag": tag}]
            )
            images = response.get("imageDetails", [])
            if not images:
                return None

            image = images[0]
            return {
                "digest": image.get("imageDigest"),
                "tags": image.get("imageTags", []),
                "pushed_at": image.get("imagePushedAt"),
                "size_bytes": image.get("imageSizeInBytes"),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "ImageNotFoundException":
                return None
            raise

    def get_latest_images(self, repo: str, limit: int = 10, tag_prefix: str = "main-") -> List[Dict]:
        """Get recent images sorted by push time, optionally filtered by tag prefix."""
        try:
            paginator = self.ecr.get_paginator("describe_images")
            all_images = []

            for page in paginator.paginate(repositoryName=repo):
                for image in page.get("imageDetails", []):
                    tags = image.get("imageTags", [])
                    # Filter by tag prefix if specified
                    if tag_prefix:
                        matching_tags = [t for t in tags if t.startswith(tag_prefix)]
                        if not matching_tags:
                            continue

                    all_images.append({
                        "digest": image.get("imageDigest"),
                        "tags": tags,
                        "pushed_at": image.get("imagePushedAt"),
                        "size_bytes": image.get("imageSizeInBytes"),
                    })

            # Sort by push time (newest first)
            all_images.sort(key=lambda x: x["pushed_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            return all_images[:limit]
        except ClientError:
            return []

    def wait_for_image(
        self,
        repo: str,
        tag: str,
        timeout: int = 1200,
        callback: Optional[Callable[[int, int, bool], None]] = None
    ) -> bool:
        """
        Poll until image is ready with exponential backoff.

        Args:
            repo: ECR repository name
            tag: Image tag to wait for
            timeout: Maximum wait time in seconds (default: 20 minutes)
            callback: Optional callback(attempt, elapsed_seconds, found) for progress updates

        Returns:
            True if image found, False if timeout
        """
        start_time = time.time()
        attempt = 0
        base_delay = 2
        max_delay = 15

        while True:
            attempt += 1
            elapsed = int(time.time() - start_time)

            # Check if image exists
            found = self.image_exists(repo, tag)

            if callback:
                callback(attempt, elapsed, found)

            if found:
                return True

            # Check timeout
            if elapsed >= timeout:
                return False

            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** min(attempt - 1, 3)), max_delay)
            jitter = random.uniform(0, delay * 0.2)
            actual_delay = delay + jitter

            # Don't sleep past timeout
            remaining = timeout - elapsed
            if actual_delay > remaining:
                actual_delay = remaining

            time.sleep(actual_delay)

    def get_deployed_tag_from_health(self, health_url: str) -> Optional[str]:
        """
        Fetch currently deployed tag from the /health endpoint.

        Args:
            health_url: URL to the health endpoint (e.g., https://app.example.com/health)

        Returns:
            The GIT_COMMIT from the health response, or None
        """
        import urllib.request
        import json

        try:
            with urllib.request.urlopen(health_url, timeout=10) as response:
                data = json.loads(response.read().decode())
                git_commit = data.get("GIT_COMMIT")
                if git_commit and git_commit != "development":
                    # Return as main-<commit> format
                    return f"main-{git_commit}"
                return None
        except Exception:
            return None
