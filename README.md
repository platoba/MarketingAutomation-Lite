# MarketingAutomation-Lite 📧

[![CI](https://github.com/platoba/MarketingAutomation-Lite/actions/workflows/ci.yml/badge.svg)](https://github.com/platoba/MarketingAutomation-Lite/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Lightweight, self-hosted marketing automation platform for cross-border e-commerce.

## Features

- **Contact Management** — Import, segment, tag contacts with custom fields; CSV export
- **Lead Scoring Engine** — Rule-based + engagement-driven contact scoring with grades (A+ to F)
- **Lifecycle Management** — Automatic lifecycle stages: subscriber → lead → MQL → SQL → customer → evangelist
- **Suppression Lists** — Global email suppression (bounce/complaint/unsubscribe/manual/compliance)
- **Email Campaigns** — Create, schedule, send HTML email campaigns via SMTP/SES
- **Email Templates** — Jinja2-powered reusable templates with variable substitution and preview
- **A/B Testing** — Test subject lines, content, send times with statistical significance
- **Automation Workflows** — Trigger-based email sequences (welcome, abandoned cart, re-engagement)
- **Webhooks** — Outbound webhook endpoints with delivery tracking and retry
- **Open/Click Tracking** — Pixel tracking for opens, redirect tracking for clicks, one-click unsubscribe
- **Analytics Dashboard** — Open rates, click rates, bounce tracking, cohort analysis, health score
- **JWT Authentication** — Secure login with Bearer token auth on all endpoints
- **REST API** — Full CRUD API with Swagger/ReDoc docs (60+ endpoints)

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: PostgreSQL 15 + Redis (SQLite for dev)
- **Task Queue**: Celery + Redis
- **Email**: SMTP / Amazon SES
- **Templates**: Jinja2 (email rendering)
- **Auth**: JWT (python-jose + passlib/bcrypt)
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

# Or use Make
make up
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run migrations
make migrate

# Start dev server
make dev

# Run tests
make test

# Lint & format
make lint
make fmt
```

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login, get JWT token |
| GET | `/api/v1/auth/me` | Current user info |

### Contacts
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/contacts/` | List contacts (filter, search, paginate) |
| POST | `/api/v1/contacts/` | Create contact |
| GET | `/api/v1/contacts/{id}` | Get contact |
| PATCH | `/api/v1/contacts/{id}` | Update contact |
| DELETE | `/api/v1/contacts/{id}` | Delete contact |
| POST | `/api/v1/contacts/import` | Bulk import (CSV) |
| GET | `/api/v1/contacts/export/csv` | Export as CSV |

### Lead Scoring (v4.0)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/scoring/rules` | Create scoring rule |
| GET | `/api/v1/scoring/rules` | List scoring rules |
| GET | `/api/v1/scoring/rules/{id}` | Get rule details |
| PATCH | `/api/v1/scoring/rules/{id}` | Update rule |
| DELETE | `/api/v1/scoring/rules/{id}` | Delete rule |
| GET | `/api/v1/scoring/contacts/{id}` | Get contact score |
| POST | `/api/v1/scoring/contacts/{id}/recalculate` | Recalculate score |
| GET | `/api/v1/scoring/contacts/{id}/history` | Score event history |
| GET | `/api/v1/scoring/leaderboard` | Top scored contacts |
| GET | `/api/v1/scoring/lifecycle` | Lifecycle distribution |
| POST | `/api/v1/scoring/events` | Award/deduct points |
| POST | `/api/v1/scoring/events/process` | Process engagement event |

### Suppression List (v4.0)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/suppression` | Add to suppression list |
| POST | `/api/v1/suppression/bulk` | Bulk suppress emails |
| GET | `/api/v1/suppression` | List suppressed emails |
| GET | `/api/v1/suppression/check?email=` | Check if suppressed |
| DELETE | `/api/v1/suppression/{email}` | Remove from list |
| GET | `/api/v1/suppression/stats` | Suppression statistics |

### Campaigns
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/campaigns/` | List campaigns |
| POST | `/api/v1/campaigns/` | Create campaign |
| POST | `/api/v1/campaigns/{id}/send` | Queue campaign for sending |

### Templates
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/templates/` | List templates |
| POST | `/api/v1/templates/` | Create template |
| POST | `/api/v1/templates/{id}/render` | Preview with variables |

### Tracking (public, no auth)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/track/open/{cid}/{uid}` | Open pixel |
| GET | `/api/v1/track/click/{cid}/{uid}?url=` | Click redirect |
| GET | `/api/v1/track/unsubscribe/{cid}/{uid}` | One-click unsubscribe |

### Workflows, A/B Testing, Webhooks & Dashboard
| Method | Path | Description |
|--------|------|-------------|
| CRUD | `/api/v1/workflows/` | Automation workflows |
| CRUD | `/api/v1/ab-tests/` | A/B test management |
| CRUD | `/api/v1/webhooks/` | Webhook endpoints |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |
| GET | `/api/v1/analytics/*` | Advanced analytics |

## Lead Scoring

The scoring engine combines three components:

| Component | Max Points | Description |
|-----------|-----------|-------------|
| **Engagement** | Unlimited | Points from email opens, clicks, form submissions (configurable rules) |
| **Profile** | 20 | Completeness of contact data (name, phone, country, custom fields) |
| **Recency** | 20 | Exponential decay — full score for recent activity, zero after 90 days |

Contacts are automatically graded and assigned lifecycle stages:

```
Grade:     A+ (90+) → A (80+) → B+ (70+) → B (60+) → C (45+) → D (25+) → F
Lifecycle: subscriber → lead → MQL → SQL → customer → evangelist
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
┌─────────────┐  ┌──────────┐  ┌──────────────┐
│  Celery     │──│  SMTP/   │  │  Scoring     │
│  Workers    │  │  SES     │  │  Engine      │
└─────────────┘  └──────────┘  └──────────────┘
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

## License

MIT
