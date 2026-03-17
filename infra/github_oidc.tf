# ---------------------------------------------------------------------------
# GitHub Actions OIDC — keyless AWS authentication for CI/CD
# ---------------------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = { Name = "${local.name}-github-oidc" }
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${local.name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json

  tags = { Name = "${local.name}-github-actions" }
}

# ---------------------------------------------------------------------------
# Permissions — scoped to the resource types Terraform manages
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "github_actions" {
  statement {
    sid    = "Terraform"
    effect = "Allow"
    actions = [
      # EC2 / VPC / Networking
      "ec2:*",
      # Lambda
      "lambda:*",
      # API Gateway
      "apigateway:*",
      # SQS
      "sqs:*",
      # ElastiCache
      "elasticache:*",
      # ECR
      "ecr:*",
      # IAM (for roles/policies managed by Terraform)
      "iam:*",
      # CloudWatch Logs
      "logs:*",
      # Secrets Manager (read-only — secrets created manually)
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      # S3 (Terraform state bucket)
      "s3:*",
      # STS (for identity checks)
      "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "terraform-deploy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}
