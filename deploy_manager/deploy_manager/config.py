"""Configuration for deployment manager."""
from typing import Dict


class Config:
    """Deployment configuration."""

    def __init__(self):
        self.region = "us-east-1"

        # ASG names
        self.blue_asg = "superschedules-prod-asg-blue"
        self.green_asg = "superschedules-prod-asg-green"

        # Target group ARNs
        self.blue_target_groups = {
            "frontend": "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-frontend-blue/b0a0d9d291710131",
            "django": "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-django-blue/176ef561d6a1f44e"
        }

        self.green_target_groups = {
            "frontend": "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-frontend-green/67f915c51f3cc58a",
            "django": "arn:aws:elasticloadbalancing:us-east-1:353130947195:targetgroup/supersched-prod-django-green/5495f976c4aab5ca"
        }
