#!/bin/bash

# Script to create ECR repositories for all Superschedules services
# Usage: ./scripts/create-ecr-repos.sh

set -e

AWS_REGION=${AWS_REGION:-us-east-1}

# List of ECR repositories to create
REPOS=(
    "superschedules-api"
    "superschedules-collector" 
    "superschedules-navigator"
    "superschedules-frontend"
)

echo "Creating ECR repositories in region: $AWS_REGION"

for repo in "${REPOS[@]}"; do
    echo "Creating repository: $repo"
    
    # Check if repository already exists
    if aws ecr describe-repositories --repository-names "$repo" --region "$AWS_REGION" >/dev/null 2>&1; then
        echo "  ✓ Repository $repo already exists"
    else
        # Create the repository
        aws ecr create-repository \
            --repository-name "$repo" \
            --region "$AWS_REGION" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256 \
            --query 'repository.repositoryUri' \
            --output text
        echo "  ✓ Created repository $repo"
    fi
    
    # Set lifecycle policy to keep only latest 10 images
    aws ecr put-lifecycle-policy \
        --repository-name "$repo" \
        --region "$AWS_REGION" \
        --lifecycle-policy-text '{
            "rules": [
                {
                    "rulePriority": 1,
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 1
                    },
                    "action": {
                        "type": "expire"
                    }
                },
                {
                    "rulePriority": 2,
                    "selection": {
                        "tagStatus": "any",
                        "countType": "imageCountMoreThan",
                        "countNumber": 10
                    },
                    "action": {
                        "type": "expire"
                    }
                }
            ]
        }' >/dev/null
    echo "  ✓ Set lifecycle policy for $repo"
    
done

echo ""
echo "✅ All ECR repositories created successfully!"
echo ""
echo "To use these repositories, set the following GitHub secrets:"
echo "  - AWS_ACCESS_KEY_ID: Your AWS access key"
echo "  - AWS_SECRET_ACCESS_KEY: Your AWS secret key"
echo "  - AWS_ACCOUNT_ID: Your AWS account ID ($(aws sts get-caller-identity --query Account --output text))"
echo ""
echo "Repository URIs:"
for repo in "${REPOS[@]}"; do
    uri=$(aws ecr describe-repositories --repository-names "$repo" --region "$AWS_REGION" --query 'repositories[0].repositoryUri' --output text)
    echo "  $repo: $uri"
done