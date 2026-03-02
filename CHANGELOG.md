## [1.2.0] - 2026-03-03

### Added
- **WhatsApp Marketing Module** — Multi-provider WhatsApp campaign management
  - WhatsApp campaign creation, scheduling, and sending
  - Twilio, MessageBird, and Vonage provider support
  - Media attachment support (images, videos, documents)
  - Delivery tracking with read receipts and reply tracking
  - Segment-based targeting
  - WhatsApp analytics (delivery rate, read rate, reply rate)
  - 8 new REST API endpoints for WhatsApp operations
  - Database migrations for `whatsapp_campaigns` and `whatsapp_logs` tables

### Technical
- New models: `WhatsAppCampaign`, `WhatsAppLog`, `WhatsAppStatus`, `WhatsAppProvider` enums
- New service: `WhatsAppService` with multi-provider abstraction
- New API router: `/api/v1/whatsapp/*` endpoints
- Test coverage for WhatsApp service and campaigns (15+ tests)
- Complete multi-channel marketing stack: Email + SMS + WhatsApp

# Changelog

## [1.1.0] - 2026-03-02

### Added
- **SMS Marketing Module** — Multi-provider SMS campaign management
  - SMS campaign creation, scheduling, and sending
  - Twilio and Aliyun SMS provider support
  - Delivery tracking and error logging
  - Segment-based targeting
  - SMS analytics and delivery reports
  - 6 new REST API endpoints for SMS operations
  - Database migrations for `sms_campaigns` and `sms_logs` tables

### Technical
- New models: `SMSCampaign`, `SMSLog`, `SMSStatus` enum
- New service: `SMSService` with provider abstraction
- New API router: `/sms/*` endpoints
- Test coverage for SMS service and providers

# Changelog

All notable changes to this project will be documented in this file.

## [4.0.0] - 2026-02-28

### Added
- **Lead Scoring Engine** — rule-based + engagement-driven contact scoring
  - Configurable scoring rules (event type, points, max per contact, decay)
  - Automatic engagement scoring from email opens, clicks, bounces
  - Profile completeness scoring (0-20 points)
  - Time-decay recency scoring (exponential decay over 90 days)
  - Contact grades: A+ / A / B+ / B / C / D / F
  - Lifecycle stages: subscriber → lead → mql → sql → customer → evangelist
  - Leaderboard API with filtering by score and lifecycle stage
  - Lifecycle distribution analytics
  - Full score event audit trail
  - Manual score award/deduction API
- **Suppression List Management** — global email suppression
  - Add/remove emails from suppression list
  - Bulk suppression endpoint
  - Suppression check before sending
  - Support for bounce/complaint/unsubscribe/manual/compliance reasons
  - Suppression statistics by reason
- **New Models**: ScoringRule, ContactScore, ScoreEvent, SuppressionList
- **New API Endpoints**: 15+ new endpoints under `/api/v1/scoring` and `/api/v1/suppression`
- **New Tests**: 48+ tests for scoring engine, lifecycle, suppression (test_scoring.py + test_suppression.py)
- CHANGELOG.md (this file)
- CONTRIBUTING.md

### Changed
- Version bumped to 4.0.0
- Updated app description to include lead scoring and suppression
- Enhanced model imports to include new lead_score models

## [3.0.0] - 2026-02-27

### Added
- A/B testing framework (ABTest, ABTestVariant models + API)
- Webhook management (endpoints + delivery tracking)
- Advanced analytics (campaign metrics, engagement reports, cohort analysis, health score)
- CSV import/export for contacts
- Email template preview/render API
- Dashboard stats, funnel analysis, contact growth charts
- JWT authentication with admin auto-setup
- Celery task queue for async email sending
- 105 tests across 11 test files

## [2.0.0] - 2026-02-27

### Added
- Automation workflows (trigger-based email sequences)
- Email open/click tracking with pixel + redirect
- Segment-based targeting
- Tag management
- Docker Compose (app + PostgreSQL + Redis)
- GitHub Actions CI pipeline

## [1.0.0] - 2026-02-27

### Added
- Initial release
- Contact management with CRUD API
- Email campaign creation and sending
- SMTP and Amazon SES backends
- FastAPI with async SQLAlchemy
- SQLite + PostgreSQL dual support
