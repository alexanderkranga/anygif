variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "nat_instance_type" {
  type    = string
  default = "t4g.small"
}

variable "pinned_ami_id" {
  type        = string
  description = "Pinned AMI ID for NAT instance (Amazon Linux 2023 ARM64)"
  default     = ""
}

variable "app_port" {
  type        = number
  default     = 8000
  description = "Port the container listens on"
}

variable "cpu" {
  type        = number
  default     = 1024
  description = "Task CPU units (1024 = 1 vCPU)"
}

variable "memory" {
  type        = number
  default     = 2048
  description = "Task memory in MB"
}

variable "min_capacity" {
  type        = number
  default     = 1
  description = "Minimum (and initial) number of ECS tasks"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Docker image tag to run. Change this to roll out a new build."
}

variable "redis_node_type" {
  type        = string
  default     = "cache.t4g.micro"
  description = "ElastiCache Redis node type"
}

# ---------------------------------------------------------------------------
# Secrets Manager ARNs — create these before applying:
#   aws secretsmanager create-secret --name anygif/telegram-bot-token     --secret-string "your-value" --region eu-central-1
#   aws secretsmanager create-secret --name anygif/telegram-webhook-secret --secret-string "your-value" --region eu-central-1
# ---------------------------------------------------------------------------

variable "telegram_bot_token_arn" {
  type        = string
  description = "Secrets Manager ARN for TELEGRAM_BOT_TOKEN"
}

variable "telegram_webhook_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for TELEGRAM_WEBHOOK_SECRET"
}

variable "generation_price_stars" {
  type        = number
  default     = 1
  description = "Price per GIF generation in Telegram Stars"
}

variable "session_ttl_seconds" {
  type        = number
  default     = 600
  description = "Session TTL in seconds"
}

variable "s3_bucket_name" {
  type        = string
  default     = "anygif-output"
  description = "S3 bucket name for GIF output"
}
