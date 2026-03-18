# ---------------------------------------------------------------------------
# SQS — payment processing queue + dead-letter queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "gif_worker_dlq" {
  name                      = "${local.name}-worker-dlq"
  message_retention_seconds = 259200 # 3 days
  sqs_managed_sse_enabled   = true

  tags = { Name = "${local.name}-worker-dlq" }
}

resource "aws_sqs_queue" "gif_worker" {
  name                       = "${local.name}-worker"
  visibility_timeout_seconds = 210 # > worker Lambda timeout (180s)
  message_retention_seconds  = 86400 # 1 day
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.gif_worker_dlq.arn
    maxReceiveCount     = 2
  })

  tags = { Name = "${local.name}-worker" }
}
