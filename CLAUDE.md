# AnyGif

Telegram bot that converts video URLs to short MP4 clips (not GIFs — Telegram auto-loops MP4). Users pay with Telegram Stars. Fully open source.

## Privacy

User privacy and anonymity are core design principles. No user-identifiable information is persisted or logged:

- **No PII in logs** — application logs contain only technical data (return codes, file sizes, durations). Subprocess output is sanitized to strip URLs before logging. CloudWatch logs auto-delete after 3 days.
- **No PII in SQS** — messages contain only `charge_id` (Telegram-generated) and `session_id` (internal UUID). No user_id, chat_id, or URLs.
- **Ephemeral session data only** — Redis stores session context (user_id, chat_id, video_url) for the payment-to-delivery handoff between Lambdas, with a 10-minute TTL. An additional `refund:{session_id}` key (1-hour TTL, deleted on use) holds only `user_id` as a refund fallback. No long-term user data storage exists anywhere.
- **Encryption at rest and in transit** — Redis (ElastiCache) uses at-rest and transit encryption (TLS). SQS queues use server-side encryption. Session data is never readable outside the Lambda runtime.
- **No names stored or parsed** — `TelegramUser` model only holds the numeric `id`. `first_name` and all other name fields are discarded at deserialization.
- **No external analytics or tracking** — no third-party services receive user data.

## Architecture

Two Lambda functions decoupled by SQS:

- **Webhook Lambda** — handles Telegram updates, validates params, sends invoices, routes payments to SQS
- **Worker Lambda** — processes payments from SQS, generates video clips, sends results or refunds

Redis (ElastiCache) stores sessions with TTL and payment dedup keys. Both Lambdas run in a VPC with a NAT instance for outbound traffic and an S3 VPC endpoint for ECR pulls.

See @infra/ for full Terraform definitions.

## Commands

```
pytest                              # unit tests (excludes integration by default)
pytest -m integration               # real network tests against video platforms
docker build --platform linux/amd64 -t anygif .
cd infra && terraform init && terraform apply
```

Deploy: push to `main` triggers GitHub Actions (@.github/workflows/deploy.yml). Region is `eu-central-1`.

## Gotchas

**Output is MP4, not GIF.** x264, 24 FPS, max 480px longest side. Telegram auto-loops it.

**Two-strategy shell script** (@anygif.sh):
1. Direct streaming — extract URL with yt-dlp, pipe to ffmpeg (fast)
2. Full download — download with yt-dlp, then process locally (reliable fallback)
TikTok always uses strategy 2. Fallback is automatic on ffmpeg failure.

**Proxy retry logic spans two layers:**
- Python (@app/gif.py) — tries without proxy first, retries with Decodo proxy on failure
- Bash (@anygif.sh) — `--proxy` flag sets `http_proxy`/`https_proxy` for both yt-dlp and ffmpeg

**Subprocess timeout is 120s** in gif.py. Worker Lambda timeout is 180s. SQS visibility timeout is 210s. Each layer is wider than the one inside it.

**Config uses lazy getter functions** (@app/config.py) — not module-level constants. This makes env vars testable via monkeypatch.

**`_ensure_init()` cold-start pattern** in both Lambda handlers — initializes Redis/Telegram clients on first invocation, not at import time.

**`asyncio.run()` per Lambda invocation** — no persistent event loop across invocations.

**Payment dedup via Redis** `SET nx` with 86400s TTL on `dedup:{charge_id}`. Prevents double-processing on Telegram webhook retries. Dedup check also guards against duplicate refunds.

**Error output is sanitized** — gif.py strips URLs from subprocess stderr to avoid leaking proxy credentials in logs/messages.

## Env Vars

Required: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `DECODO_PROXY_URL` (worker only), `SQS_QUEUE_URL` (webhook only). All injected by Terraform from Secrets Manager.

Optional with defaults: `REDIS_URL` (localhost:6379), `GENERATION_PRICE_STARS` (10), `SESSION_TTL_SECONDS` (600).

## Testing

See @tests/conftest.py for fixtures: `fake_redis`, `telegram_calls` (mock API tracker), and pre-set env vars. Integration tests use `@pytest.mark.integration` and are excluded by default. They auto-skip if network is unavailable.
