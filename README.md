# MarketingAutomation-Lite 📧

Lightweight, self-hosted marketing automation platform for cross-border e-commerce.

## Features

- **Contact Management** — Import, segment, tag contacts with custom fields
- **Email Campaigns** — Create, schedule, send HTML email campaigns via SMTP/SES
- **Automation Workflows** — Trigger-based email sequences (welcome, abandoned cart, re-engagement)
- **Analytics Dashboard** — Open rates, click rates, bounce tracking
- **REST API** — Full CRUD API for integration with other tools
- **Multi-tenant** — Support multiple brands/stores from one instance

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: PostgreSQL 15 + Redis
- **Task Queue**: Celery + Redis
- **Email**: SMTP / Amazon SES / SendGrid
- **Frontend**: Jinja2 templates + HTMX (lightweight, no SPA)
- **Deployment**: Docker Compose

## Quick Start

```bash
# Clone
git clone https://github.com/platoba/MarketingAutomation-Lite.git
cd MarketingAutomation-Lite

# Configure
cp .env.example .env
# Edit .env with your SMTP/database settings

# Run with Docker
docker compose up -d

# Access
open http://localhost:8000
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest -v
```

## API Docs

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌─────────┐
│  FastAPI     │────▶│ PostgreSQL│     │  Redis   │
│  (Web+API)  │     └──────────┘     └────┬────┘
└──────┬──────┘                           │
       │              ┌───────────────────┘
       ▼              ▼
┌─────────────┐  ┌──────────┐
│  Celery     │──│  SMTP/   │
│  Workers    │  │  SES     │
└─────────────┘  └──────────┘
```

## License

MIT
