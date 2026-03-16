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
}

# ---------------------------------------------------------------------------
# VPC Link — connects API Gateway to internal ALB
# ---------------------------------------------------------------------------

resource "aws_security_group" "vpc_link" {
  name        = "anygif-vpc-link"
  description = "API Gateway VPC Link for anygif"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "anygif-vpc-link" }
}

resource "aws_security_group_rule" "vpc_link_to_alb" {
  type                     = "egress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  security_group_id        = aws_security_group.vpc_link.id
  source_security_group_id = aws_security_group.alb.id
  description              = "HTTP to internal ALB"
}

resource "aws_apigatewayv2_vpc_link" "main" {
  name               = "anygif"
  security_group_ids = [aws_security_group.vpc_link.id]
  subnet_ids         = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = { Name = "anygif-vpc-link" }
}

# ---------------------------------------------------------------------------
# Integration + Route — POST /webhook → ALB
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "alb" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "HTTP_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lb_listener.http.arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.main.id
}

resource "aws_apigatewayv2_route" "webhook" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.alb.id}"
}
