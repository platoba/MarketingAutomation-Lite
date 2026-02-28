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
