# ---------------------------------------------------------------------------
# IAM role — shared by both Lambda functions
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = { Name = "${local.name}-lambda" }
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "lambda_sqs" {
  name = "sqs-send"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
      ]
      Resource = [
        aws_sqs_queue.gif_worker.arn,
        aws_sqs_queue.gif_worker_dlq.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy" "lambda_secrets" {
  name = "secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        var.telegram_bot_token_arn,
        var.telegram_webhook_secret_arn,
        var.decodo_proxy_url_arn,
      ]
    }]
  })
}

# ---------------------------------------------------------------------------
# Secrets — read at apply time, inject as env vars
# ---------------------------------------------------------------------------

data "aws_secretsmanager_secret_version" "bot_token" {
  secret_id = var.telegram_bot_token_arn
}

data "aws_secretsmanager_secret_version" "webhook_secret" {
  secret_id = var.telegram_webhook_secret_arn
}

data "aws_secretsmanager_secret_version" "decodo_proxy_url" {
  secret_id = var.decodo_proxy_url_arn
}

# ---------------------------------------------------------------------------
# Security group — Lambda
# ---------------------------------------------------------------------------

resource "aws_security_group" "lambda" {
  name        = "${local.name}-lambda"
  description = "Lambda functions for ${local.name}"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Outbound for Telegram API, yt-dlp, Redis"
  }

  tags = { Name = "${local.name}-lambda" }
}

# ---------------------------------------------------------------------------
# CloudWatch log groups
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "webhook" {
  name              = "/aws/lambda/${local.name}-webhook"
  retention_in_days = 3
  tags              = { Name = "${local.name}-webhook" }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.name}-worker"
  retention_in_days = 3
  tags              = { Name = "${local.name}-worker" }
}

# ---------------------------------------------------------------------------
# Lambda functions
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "webhook" {
  function_name = "${local.name}-webhook"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  timeout       = 29
  memory_size   = var.webhook_memory

  image_config {
    command = ["app.lambda_webhook.handler"]
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      TELEGRAM_BOT_TOKEN     = data.aws_secretsmanager_secret_version.bot_token.secret_string
      TELEGRAM_WEBHOOK_SECRET = data.aws_secretsmanager_secret_version.webhook_secret.secret_string
      REDIS_URL              = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379"
      GENERATION_PRICE_STARS = tostring(var.generation_price_stars)
      SESSION_TTL_SECONDS    = tostring(var.session_ttl_seconds)
      SQS_QUEUE_URL          = aws_sqs_queue.gif_worker.url
    }
  }

  depends_on = [aws_cloudwatch_log_group.webhook]

  tags = { Name = "${local.name}-webhook" }
}

resource "aws_lambda_function" "worker" {
  function_name = "${local.name}-worker"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  timeout       = var.worker_timeout
  memory_size   = var.worker_memory

  image_config {
    command = ["app.lambda_worker.handler"]
  }

  vpc_config {
    subnet_ids         = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  ephemeral_storage {
    size = 1024
  }

  environment {
    variables = {
      TELEGRAM_BOT_TOKEN     = data.aws_secretsmanager_secret_version.bot_token.secret_string
      TELEGRAM_WEBHOOK_SECRET = data.aws_secretsmanager_secret_version.webhook_secret.secret_string
      REDIS_URL              = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379"
      GENERATION_PRICE_STARS = tostring(var.generation_price_stars)
      SESSION_TTL_SECONDS    = tostring(var.session_ttl_seconds)
      DECODO_PROXY_URL       = data.aws_secretsmanager_secret_version.decodo_proxy_url.secret_string
    }
  }

  depends_on = [aws_cloudwatch_log_group.worker]

  tags = { Name = "${local.name}-worker" }
}

# ---------------------------------------------------------------------------
# SQS → Worker event source mapping
# ---------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn = aws_sqs_queue.gif_worker.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1
}

# ---------------------------------------------------------------------------
# API Gateway → Webhook Lambda permission
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
