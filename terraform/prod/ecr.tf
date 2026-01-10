# ECR Repositories for Superschedules services with lifecycle policies

locals {
  ecr_repos = {
    frontend  = "superschedules-frontend"  # Used as nginx
    api       = "superschedules-api"       # Used as django
    navigator = "superschedules-navigator" # Used as fastapi
    collector = "superschedules-collector"
  }

  # Shared lifecycle policy: keep main-* tags for rollback
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Delete untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 20 main-* tagged images for rollback"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["main-"]
          countType     = "imageCountMoreThan"
          countNumber   = 20
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Keep last 5 other tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["latest", "dev-", "staging-"]
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# Frontend repository (nginx)
resource "aws_ecr_repository" "frontend" {
  name                 = local.ecr_repos.frontend
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(
    var.default_tags,
    {
      Name = local.ecr_repos.frontend
    }
  )
}

resource "aws_ecr_lifecycle_policy" "nginx" {
  repository = aws_ecr_repository.frontend.name
  policy     = local.ecr_lifecycle_policy
}

# API repository (django)
resource "aws_ecr_repository" "api" {
  name                 = local.ecr_repos.api
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(
    var.default_tags,
    {
      Name = local.ecr_repos.api
    }
  )
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy     = local.ecr_lifecycle_policy
}

# Navigator repository (fastapi)
resource "aws_ecr_repository" "navigator" {
  name                 = local.ecr_repos.navigator
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(
    var.default_tags,
    {
      Name = local.ecr_repos.navigator
    }
  )
}

resource "aws_ecr_lifecycle_policy" "navigator" {
  repository = aws_ecr_repository.navigator.name
  policy     = local.ecr_lifecycle_policy
}

# Collector repository
resource "aws_ecr_repository" "collector" {
  name                 = local.ecr_repos.collector
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(
    var.default_tags,
    {
      Name = local.ecr_repos.collector
    }
  )
}

resource "aws_ecr_lifecycle_policy" "collector" {
  repository = aws_ecr_repository.collector.name
  policy     = local.ecr_lifecycle_policy
}
