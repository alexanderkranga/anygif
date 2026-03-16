provider "aws" {
  region = "eu-central-1"
}

terraform {
  backend "s3" {
    bucket = "anygif-terraform-state"
    region = "eu-central-1"
    key    = "prod/terraform.tfstate"
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}
