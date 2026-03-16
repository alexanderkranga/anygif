#!/usr/bin/env bash
# Build the anygif Docker image, push it to ECR, and trigger a rolling deploy.
#
# Usage:
#   ./deploy.sh                  # build + push + deploy
#   IMAGE_TAG=abc123 ./deploy.sh # push a specific tag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS_REGION="${AWS_REGION:-eu-central-1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Read ECR repo URL from Terraform state
INFRA_DIR="$SCRIPT_DIR/infra"
echo "Reading ECR repository URL from Terraform state..."
ECR_REPO_URL=$(cd "$INFRA_DIR" && terraform output -raw ecr_repository_url)

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

echo "Building Docker image (linux/amd64)..."
docker build --platform linux/amd64 -t "anygif:$IMAGE_TAG" "$SCRIPT_DIR"

echo "Tagging..."
docker tag "anygif:$IMAGE_TAG" "$ECR_REPO_URL:$IMAGE_TAG"

echo "Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "Pushing..."
docker push "$ECR_REPO_URL:$IMAGE_TAG"

echo ""
echo "Pushed: $ECR_REPO_URL:$IMAGE_TAG"
echo ""
echo "To trigger a rolling deployment run:"
echo "  aws ecs update-service --cluster anygif --service anygif --force-new-deployment --region $AWS_REGION"
