#!/bin/bash
set -e

echo "Creating IAM policy for Secrets Manager access..."

# Create the IAM policy
POLICY_ARN=$(aws iam create-policy \
  --policy-name superschedules-prod-secrets-access \
  --description "Allow EC2 instances to read application secrets from Secrets Manager" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ],
        "Resource": "arn:aws:secretsmanager:us-east-1:353130947195:secret:prod/superschedules/secrets-*"
      }
    ]
  }' \
  --query 'Policy.Arn' \
  --output text 2>/dev/null || \
  echo "arn:aws:iam::353130947195:policy/superschedules-prod-secrets-access")

echo "Policy ARN: $POLICY_ARN"

# Attach the policy to the EC2 role
echo "Attaching policy to superschedules-prod-ec2-role..."
aws iam attach-role-policy \
  --role-name superschedules-prod-ec2-role \
  --policy-arn "$POLICY_ARN"

echo "✅ IAM policy created and attached successfully!"
echo ""
echo "Now you can import it into Terraform state:"
echo "cd terraform/prod"
echo "terraform import aws_iam_policy.secrets_access $POLICY_ARN"
echo "terraform import aws_iam_role_policy_attachment.secrets_access superschedules-prod-ec2-role/arn:aws:iam::353130947195:policy/superschedules-prod-secrets-access"
