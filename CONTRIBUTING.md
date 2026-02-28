# Contributing to MarketingAutomation-Lite

Thank you for your interest in contributing! This document provides guidelines and instructions.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/platoba/MarketingAutomation-Lite.git
cd MarketingAutomation-Lite

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
```

## Running Tests

```bash
# Run all tests
make test

# Run with coverage
pytest --cov=app tests/ -v

# Run specific test file
pytest tests/test_scoring.py -v
```

## Code Style

- Python 3.11+
- Type hints for all function signatures
- Docstrings for public functions and classes
- Use `ruff` for linting: `make lint`

## Project Structure

```
app/
├── api/          # FastAPI route handlers
├── models/       # SQLAlchemy models
├── schemas/      # Pydantic request/response schemas
├── services/     # Business logic
├── tasks/        # Celery background tasks
├── config.py     # Settings management
├── database.py   # DB engine setup
└── main.py       # App entry point
tests/            # Test files (pytest)
```

## Adding Features

1. **Models** → `app/models/` — Add SQLAlchemy model, import in `__init__.py`
2. **Service** → `app/services/` — Business logic, DB queries
3. **API** → `app/api/` — FastAPI router, register in `main.py`
4. **Tests** → `tests/test_*.py` — At least 80% coverage for new code
5. **Docs** → Update README.md and CHANGELOG.md

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for new functionality
4. Ensure all tests pass: `make test`
5. Lint your code: `make lint`
6. Update CHANGELOG.md
7. Submit a pull request with a clear description

## Commit Messages

Follow conventional commits:

```
feat: add lead scoring engine
fix: correct bounce rate calculation
docs: update API documentation
test: add suppression list tests
chore: update dependencies
```

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
