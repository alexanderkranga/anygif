# ---------------------------------------------------------------------------
# Security group — Redis
# ---------------------------------------------------------------------------

resource "aws_security_group" "redis" {
  name        = "anygif-redis"
  description = "ElastiCache Redis for anygif"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "Redis from Lambda functions"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "anygif-redis" }
}

# ---------------------------------------------------------------------------
# ElastiCache subnet group
# ---------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "main" {
  name       = "anygif"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  tags = { Name = "anygif" }
}

# ---------------------------------------------------------------------------
# ElastiCache Redis (single node, no cluster mode)
# ---------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "anygif"
  description          = "AnyGif Redis - sessions and dedup"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  num_cache_clusters   = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = false

  tags = { Name = "anygif-redis" }
}
