output "webhook_url" {
  value       = "${aws_apigatewayv2_api.main.api_endpoint}/webhook"
  description = "Webhook URL to register with Telegram"
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "ECR repository URL — push images here"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.gif_output.id
  description = "S3 bucket for GIF output"
}

output "redis_endpoint" {
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  description = "ElastiCache Redis endpoint"
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "ECS cluster name"
}

output "ecs_service_name" {
  value       = aws_ecs_service.app.name
  description = "ECS service name"
}
