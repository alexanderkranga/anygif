# ---------------------------------------------------------------------------
# S3 bucket — durable GIF generation counter
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "stats" {
  bucket = "${local.name}-stats-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name}-stats" }
}

resource "aws_s3_bucket_public_access_block" "stats" {
  bucket                  = aws_s3_bucket.stats.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_role_policy" "lambda_stats_s3" {
  name = "stats-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject"]
      Resource = "${aws_s3_bucket.stats.arn}/stats.json"
    }]
  })
}

output "stats_bucket_name" {
  value = aws_s3_bucket.stats.bucket
}
