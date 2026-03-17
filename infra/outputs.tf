output "webhook_url" {
  value       = "${aws_apigatewayv2_api.main.api_endpoint}/webhook"
  description = "Webhook URL to register with Telegram"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "ECR repository URL — push images here"
}


output "redis_endpoint" {
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  description = "ElastiCache Redis endpoint"
}

output "webhook_lambda_name" {
  value       = aws_lambda_function.webhook.function_name
  description = "Webhook Lambda function name"
}

output "worker_lambda_name" {
  value       = aws_lambda_function.worker.function_name
  description = "Worker Lambda function name"
}

output "sqs_queue_url" {
  value       = aws_sqs_queue.gif_worker.url
  description = "SQS queue URL for GIF worker"
}

output "dlq_url" {
  value       = aws_sqs_queue.gif_worker_dlq.url
  description = "Dead-letter queue URL for failed payments"
}

output "github_actions_role_arn" {
  value       = aws_iam_role.github_actions.arn
  description = "IAM role ARN for GitHub Actions OIDC — add to GitHub Secrets as AWS_ROLE_ARN"
}
