"""Lambda function to update Route53 A records when prod-lite instance launches.

Triggered by ASG lifecycle hook via EventBridge when instance launches.
Updates all configured domain A records to point to the new instance's public IP.
"""

import json
import os
import time

import boto3


def handler(event, context):
    """Handle ASG lifecycle hook event and update DNS."""
    print(f"Event received: {json.dumps(event)}")

    # Extract event details
    detail = event.get("detail", {})
    instance_id = detail.get("EC2InstanceId")
    asg_name = detail.get("AutoScalingGroupName")
    lifecycle_hook_name = detail.get("LifecycleHookName")
    lifecycle_action_token = detail.get("LifecycleActionToken")

    if not instance_id:
        print("ERROR: No instance ID in event")
        return {"statusCode": 400, "body": "No instance ID"}

    print(f"Processing instance: {instance_id}")

    ec2 = boto3.client("ec2")
    route53 = boto3.client("route53")
    autoscaling = boto3.client("autoscaling")

    # Wait for instance to get a public IP (with retries)
    public_ip = None
    for attempt in range(10):
        response = ec2.describe_instances(InstanceIds=[instance_id])
        try:
            instance = response["Reservations"][0]["Instances"][0]
            public_ip = instance.get("PublicIpAddress")
            if public_ip:
                print(f"Instance {instance_id} has public IP: {public_ip}")
                break
        except (IndexError, KeyError) as e:
            print(f"Error getting instance details: {e}")

        print(f"Attempt {attempt + 1}: No public IP yet, waiting 5s...")
        time.sleep(5)

    if not public_ip:
        print(f"ERROR: Instance {instance_id} has no public IP after 50s")
        # Complete lifecycle action to avoid blocking ASG
        _complete_lifecycle_action(
            autoscaling, lifecycle_hook_name, asg_name, lifecycle_action_token
        )
        return {"statusCode": 500, "body": "Instance has no public IP"}

    # Get configuration from environment
    hosted_zone_id = os.environ["HOSTED_ZONE_ID"]
    domains = [d.strip() for d in os.environ["DOMAINS"].split(",") if d.strip()]
    ttl = int(os.environ.get("TTL", "60"))

    print(f"Updating Route53 zone {hosted_zone_id} for domains: {domains}")

    # Build Route53 change batch
    changes = []
    for domain in domains:
        changes.append(
            {
                "Action": "UPSERT",
                "ResourceRecordSet": {
                    "Name": domain,
                    "Type": "A",
                    "TTL": ttl,
                    "ResourceRecords": [{"Value": public_ip}],
                },
            }
        )

    if changes:
        try:
            response = route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={
                    "Comment": f"Auto-update for prod-lite instance {instance_id}",
                    "Changes": changes,
                },
            )
            print(f"Route53 update response: {response}")
        except Exception as e:
            print(f"ERROR updating Route53: {e}")
            # Still complete lifecycle action to avoid blocking
            _complete_lifecycle_action(
                autoscaling, lifecycle_hook_name, asg_name, lifecycle_action_token
            )
            return {"statusCode": 500, "body": str(e)}

    # Complete lifecycle action
    _complete_lifecycle_action(
        autoscaling, lifecycle_hook_name, asg_name, lifecycle_action_token
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "instance_id": instance_id,
                "public_ip": public_ip,
                "domains_updated": domains,
            }
        ),
    }


def _complete_lifecycle_action(
    autoscaling, lifecycle_hook_name, asg_name, lifecycle_action_token
):
    """Complete the ASG lifecycle action to allow instance to proceed."""
    if lifecycle_hook_name and lifecycle_action_token:
        try:
            autoscaling.complete_lifecycle_action(
                LifecycleHookName=lifecycle_hook_name,
                AutoScalingGroupName=asg_name,
                LifecycleActionToken=lifecycle_action_token,
                LifecycleActionResult="CONTINUE",
            )
            print("Lifecycle action completed successfully")
        except Exception as e:
            print(f"WARNING: Failed to complete lifecycle action: {e}")
    else:
        print("No lifecycle hook info - skipping completion")
