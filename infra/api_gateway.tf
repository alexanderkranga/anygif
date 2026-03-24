# ---------------------------------------------------------------------------
# API Gateway HTTP API — provides HTTPS endpoint for Telegram webhook
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "main" {
  name          = "anygif"
  protocol_type = "HTTP"
  description   = "AnyGIF Telegram bot webhook"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  route_settings {
    route_key              = "GET /stats"
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
}

# ---------------------------------------------------------------------------
# Integration + Route — POST /webhook → Lambda
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "stats" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /stats"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

output "api_endpoint" {
  value       = aws_apigatewayv2_api.main.api_endpoint
  description = "Base URL for API Gateway — use <api_endpoint>/stats for the counter"
}
