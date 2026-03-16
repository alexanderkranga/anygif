locals {
  name = "anygif"
}

# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Internal ALB for ${local.name}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.vpc_link.id]
    description     = "HTTP from API Gateway VPC Link"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${local.name}-tasks"
  description = "ECS tasks for ${local.name}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
    description     = "Traffic from ALB"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Outbound for Telegram API, yt-dlp, Redis, S3"
  }

  tags = { Name = "${local.name}-tasks" }
}

# ---------------------------------------------------------------------------
# ALB (internal — only reachable via API Gateway VPC Link)
# ---------------------------------------------------------------------------

resource "aws_lb" "app" {
  name               = local.name
  load_balancer_type = "application"
  internal           = true
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = { Name = local.name }
}

# ---------------------------------------------------------------------------
# Target group
# ---------------------------------------------------------------------------

resource "aws_lb_target_group" "app" {
  name        = local.name
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 10
  }

  tags = { Name = local.name }
}

# ---------------------------------------------------------------------------
# Listener — HTTP only (HTTPS terminates at API Gateway)
# ---------------------------------------------------------------------------

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
