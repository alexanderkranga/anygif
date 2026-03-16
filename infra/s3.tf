# ---------------------------------------------------------------------------
# S3 bucket for GIF output — 7-day lifecycle expiration
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "gif_output" {
  bucket = var.s3_bucket_name

  tags = { Name = "anygif-gif-output" }
}

resource "aws_s3_bucket_lifecycle_configuration" "gif_output" {
  bucket = aws_s3_bucket.gif_output.id

  rule {
    id     = "expire-gifs"
    status = "Enabled"

    expiration {
      days = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "gif_output" {
  bucket = aws_s3_bucket.gif_output.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
