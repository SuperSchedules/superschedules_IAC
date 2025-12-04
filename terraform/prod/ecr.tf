# ECR Repositories for Superschedules services with lifecycle policies

locals {
  ecr_repos = {
    frontend  = "superschedules-frontend"  # Used as nginx
    api       = "superschedules-api"       # Used as django
    navigator = "superschedules-navigator" # Used as fastapi
    collector = "superschedules-collector"
  }
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
  policy = jsonencode({
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
        description  = "Keep last 3 images, delete others"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
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
  policy = jsonencode({
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
        description  = "Keep last 3 images, delete others"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
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
  policy = jsonencode({
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
        description  = "Keep last 3 images, delete others"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
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
  policy = jsonencode({
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
        description  = "Keep last 3 images, delete others"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
