# MarketingAutomation-Lite 📧

Lightweight, self-hosted marketing automation platform for cross-border e-commerce.

## Features

- **Contact Management** — Import, segment, tag contacts with custom fields; CSV export
- **Email Campaigns** — Create, schedule, send HTML email campaigns via SMTP/SES
- **Email Templates** — Jinja2-powered reusable templates with variable substitution and preview
- **Automation Workflows** — Trigger-based email sequences (welcome, abandoned cart, re-engagement)
- **Open/Click Tracking** — Pixel tracking for opens, redirect tracking for clicks, one-click unsubscribe
- **Analytics Dashboard** — Open rates, click rates, bounce tracking
- **JWT Authentication** — Secure login with Bearer token auth on all endpoints
- **REST API** — Full CRUD API with Swagger/ReDoc docs
- **Multi-tenant** — Support multiple brands/stores from one instance

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: PostgreSQL 15 + Redis
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
| POST | `/api/v1/contacts/import` | Bulk import |
| GET | `/api/v1/contacts/export/csv` | Export as CSV |

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

### Workflows & Dashboard
| Method | Path | Description |
|--------|------|-------------|
| CRUD | `/api/v1/workflows/` | Automation workflows |
| GET | `/api/v1/dashboard/stats` | Dashboard statistics |

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
