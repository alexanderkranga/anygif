# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "anygif" }
}

# ---------------------------------------------------------------------------
# Subnets — 2 public (NAT instance), 2 private (ECS + Redis + ALB)
# ---------------------------------------------------------------------------

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.101.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "anygif-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.102.0/24"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true
  tags                    = { Name = "anygif-public-b" }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  tags              = { Name = "anygif-private-a" }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]
  tags              = { Name = "anygif-private-b" }
}

# ---------------------------------------------------------------------------
# Internet gateway
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "anygif-igw" }
}

# ---------------------------------------------------------------------------
# S3 VPC endpoint (free, used by ECR image pulls + GIF uploads)
# ---------------------------------------------------------------------------

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${data.aws_region.current.id}.s3"

  route_table_ids = [
    aws_route_table.private_a.id,
    aws_route_table.private_b.id,
  ]

  tags = { Name = "anygif-s3-endpoint" }
}

# ---------------------------------------------------------------------------
# NAT instance (cheap alternative to NAT Gateway)
# ---------------------------------------------------------------------------

locals {
  nat_ami_id = var.pinned_ami_id != "" ? var.pinned_ami_id : data.aws_ami.al2023_arm64.id
}

data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-*-arm64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_iam_role" "nat_instance" {
  name = "anygif-nat-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = { Name = "anygif-nat-instance" }
}

resource "aws_iam_role_policy_attachment" "nat_ssm" {
  role       = aws_iam_role.nat_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "nat_instance" {
  name = "anygif-nat-instance"
  role = aws_iam_role.nat_instance.name
}

resource "aws_eip" "nat" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.main]
  tags       = { Name = "anygif-nat-eip" }
}

resource "aws_instance" "nat" {
  ami                    = local.nat_ami_id
  instance_type          = var.nat_instance_type
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.nat_instance.id]
  iam_instance_profile   = aws_iam_instance_profile.nat_instance.name
  source_dest_check      = false

  user_data = <<-EOF
#!/bin/bash
set -euxo pipefail
yum install iptables-services -y
systemctl enable iptables
systemctl start iptables
echo "net.ipv4.ip_forward = 1" | tee /etc/sysctl.d/custom-ip-forwarding.conf
sysctl -p /etc/sysctl.d/custom-ip-forwarding.conf
/sbin/iptables -t nat -A POSTROUTING -o ens5 -j MASQUERADE
/sbin/iptables -F FORWARD
service iptables save
EOF

  tags = { Name = "anygif-nat-instance" }
}

resource "aws_eip_association" "nat" {
  instance_id   = aws_instance.nat.id
  allocation_id = aws_eip.nat.id
}

# ---------------------------------------------------------------------------
# Security group — NAT instance
# ---------------------------------------------------------------------------

resource "aws_security_group" "nat_instance" {
  name        = "anygif-nat-instance"
  description = "NAT instance for anygif"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_subnet.private_a.cidr_block, aws_subnet.private_b.cidr_block]
    description = "All traffic from private subnets"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "anygif-nat-instance" }
}

# ---------------------------------------------------------------------------
# Route tables
# ---------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "anygif-public" }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private_a" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_instance.nat.primary_network_interface_id
  }

  tags = { Name = "anygif-private-a" }
}

resource "aws_route_table" "private_b" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_instance.nat.primary_network_interface_id
  }

  tags = { Name = "anygif-private-b" }
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private_a.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private_b.id
}
