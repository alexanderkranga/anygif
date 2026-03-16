# ---------------------------------------------------------------------------
# ECR repository
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "app" {
  name                 = "anygif"
  image_tag_mutability = "MUTABLE"

  tags = { Name = "anygif" }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
