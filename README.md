# Swarm Engine (Upgraded)

This is the fully upgraded lightweight swarm engine for job matching.  
It includes all fixes and enhancements for production readiness.

## Features

- Two‑phase scraping with job description extraction.
- Notification deduplication (sends alerts only once per job).
- Feedback integration in scoring.
- Correct signal handling and cycle isolation.
- Shared HTTP sessions for efficiency.
- Optional dashboard with feedback and manual scan endpoints.
- Structured JSON logging.
- Prometheus metrics.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Install Playwright browsers: `playwright install chromium`
3. Copy `.env.example` to `.env` and fill in your API keys and settings.
4. Run: `python main.py`

## Configuration

All configuration is via environment variables (or `.env`). See `config.py` for all options.

## Dashboard

Set `ENABLE_DASHBOARD=true` to start the FastAPI dashboard. Endpoints:
- `GET /health`
- `GET /metrics` (requires API key)
- `GET /jobs` (requires API key)
- `GET /report` (requires API key)
- `POST /feedback` (requires API key)
- `POST /scan` (requires API key, triggers a scan cycle)

## Notifications

Set `SLACK_WEBHOOK_URL` or `DISCORD_WEBHOOK_URL` for real-time alerts. Notifications are sent only once per job.

## Testing

Run `pytest` to execute unit tests.
