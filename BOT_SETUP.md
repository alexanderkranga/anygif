# AnyGIF Bot — Deployment Guide

## Prerequisites

- AWS CLI configured with credentials for the target account
- Terraform installed
- Docker installed
- Region: `eu-central-1`

---

## Step 1: Create the Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts to pick a name and username
3. Copy the bot token BotFather gives you — you'll need it in Step 3
4. Send `/mybots` → select your bot → **Bot Settings** → **Payments** → choose **Telegram Stars** as the payment provider (no external provider needed — Stars is built-in)

## Step 2: Generate a Webhook Secret

Pick a random string to use as webhook secret. This prevents unauthorized POST requests to your webhook endpoint.

```bash
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "$WEBHOOK_SECRET"
```

Save this value — you'll need it in Step 3 and Step 7.

## Step 3: Create Secrets in AWS Secrets Manager

```bash
aws secretsmanager create-secret \
  --name anygif/telegram-bot-token \
  --secret-string "YOUR_BOT_TOKEN_HERE" \
  --region eu-central-1

aws secretsmanager create-secret \
  --name anygif/telegram-webhook-secret \
  --secret-string "YOUR_WEBHOOK_SECRET_HERE" \
  --region eu-central-1
```

Note the ARN from each command's output — you'll need them in Step 5.

## Step 4: Create the Terraform State Bucket

```bash
aws s3 mb s3://anygif-terraform-state --region eu-central-1
```

## Step 5: Create `infra/terraform.tfvars`

Create the file `infra/terraform.tfvars` with the ARNs from Step 3:

```hcl
telegram_bot_token_arn     = "arn:aws:secretsmanager:eu-central-1:ACCOUNT_ID:secret:anygif/telegram-bot-token-XXXXXX"
telegram_webhook_secret_arn = "arn:aws:secretsmanager:eu-central-1:ACCOUNT_ID:secret:anygif/telegram-webhook-secret-XXXXXX"
```

## Step 6: Deploy Infrastructure

```bash
cd infra
terraform init
terraform plan    # review the plan
terraform apply   # type "yes" to confirm
```

This creates: VPC, subnets, NAT instance, internal ALB, API Gateway, ECS cluster, ElastiCache Redis, S3 bucket, ECR repository.

After apply completes, note the outputs:

```bash
terraform output webhook_url        # you'll need this in Step 8 https://sn3k1fhq5e.execute-api.eu-central-1.amazonaws.com/webhook
terraform output ecr_repository_url # deploy.sh reads this automatically 347416517150.dkr.ecr.eu-central-1.amazonaws.com/anygif
```

## Step 7: Build and Push the Docker Image

From the project root:

```bash
./deploy.sh
```

This builds the image for `linux/amd64`, pushes it to ECR, and prints the image URI.

## Step 8: Trigger ECS Deployment

```bash
aws ecs update-service \
  --cluster anygif \
  --service anygif \
  --force-new-deployment \
  --region eu-central-1
```

Wait for the service to stabilize:

```bash
aws ecs wait services-stable \
  --cluster anygif \
  --services anygif \
  --region eu-central-1
```

## Step 9: Register the Webhook with Telegram

Replace `<BOT_TOKEN>`, `<WEBHOOK_URL>`, and `<WEBHOOK_SECRET>` with your values:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<WEBHOOK_URL>&secret_token=<WEBHOOK_SECRET>"
```

You should get `{"ok":true,"result":true,"description":"Webhook was set"}`.

Verify:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

## Step 10: Test the Bot

1. Open your bot in Telegram
2. Send `/start` — you should get a welcome message
3. Send `/gif https://www.youtube.com/watch?v=dQw4w9WgXcQ 0:43 5`
4. Pay the 1 Star invoice
5. Receive your GIF

---

## Ongoing Operations

### Redeploy after code changes

```bash
./deploy.sh
aws ecs update-service --cluster anygif --service anygif --force-new-deployment --region eu-central-1
```

### View logs

```bash
aws logs tail /ecs/anygif --follow --region eu-central-1
```

### Update a secret

```bash
aws secretsmanager put-secret-value \
  --secret-id anygif/telegram-bot-token \
  --secret-string "NEW_VALUE" \
  --region eu-central-1

# Then force a new deployment to pick up the change:
aws ecs update-service --cluster anygif --service anygif --force-new-deployment --region eu-central-1
```

### Tear down everything

```bash
cd infra
terraform destroy
aws s3 rb s3://anygif-terraform-state --force
```
