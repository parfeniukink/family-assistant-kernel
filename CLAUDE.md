# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Family Budget Bot - a REST API for managing shared family finances (transactions, analytics) built with FastAPI, PostgreSQL, and memcached. Uses DDD-inspired architecture with CQS (Command Query Separation) pattern for async database operations.

## Commands

```bash
# Dependencies (pip-tools)
make install          # sync dev dependencies
make lock             # pin dependencies to requirements/*.txt
make upgrade          # upgrade all dependencies

# Run application
make infra            # start database and cache containers
make run              # dev server (uvicorn --reload on port 8001)
make migrate          # run alembic migrations

# Testing
make test             # run all tests
make xtest            # run tests in parallel (4 workers)
python -m pytest tests/path/to/test_file.py::test_function  # single test

# Code quality
make fix              # format with black + isort
make check            # lint (flake8, isort, black, mypy)
```

## Architecture

```
src/
├── main.py              # FastAPI app entrypoint
├── http/                # Presentation tier
│   ├── resources/       # API endpoints (routers)
│   └── contracts/       # Request/response Pydantic schemas
├── application/         # Application tier (use cases, orchestration)
│   ├── authentication.py  # Login, token refresh, logout
│   ├── analytics.py       # Analytics use cases
│   ├── news.py            # AI-powered news extension
│   ├── notifications.py   # Notification orchestration
│   ├── scheduler.py       # Job scheduling orchestration
│   ├── transactions.py    # Transaction CRUD orchestration
│   └── users.py           # User operations
├── domain/              # Pure business model (zero infra deps)
│   ├── entities.py        # InternalData base class
│   ├── types.py           # Shared type literals (IncomeSource)
│   ├── equity/            # Currency and equity entities
│   ├── jobs/              # Job entities and type registry
│   ├── news/              # NewsItem entity
│   ├── notifications/     # Notification entities
│   ├── transactions/      # cost.py, income.py, exchange.py, value_objects.py
│   └── users/             # User and UserConfiguration entities
├── infrastructure/      # Infrastructure tier
│   ├── agents/            # AI model setup (pydantic_ai)
│   ├── database/          # SQLAlchemy ORM, CQS, DataAccessLayer (dal.py)
│   ├── jobs/hooks/        # Job type handlers (news, relevance)
│   ├── repositories/      # Per-aggregate repositories
│   ├── query_services/    # Read-only query services (analytics)
│   ├── security.py        # Password hashing (Argon2), JWT
│   ├── cache.py           # Memcached client
│   └── hooks.py           # App lifespan (startup/shutdown)
└── integrations/        # External services (monobank)
```

### Key Patterns

**Repository Pattern**: Per-aggregate repositories in `src/infrastructure/repositories/` extend `DataAccessLayer` base class (in `database/dal.py`). Each repository manages its own session lifecycle:

```python
from src.infrastructure import database, repositories

# Write operation - repo manages session, flush() commits
repo = repositories.Cost()
item = await repo.add_cost(candidate)
await repo.flush()

# Read operation - no flush needed
items = await repositories.Cost().costs(offset=0, limit=10)

# Cross-repo transaction (shared session for atomicity)
async with database.transaction() as session:
    cost_repo = repositories.Cost(session=session)
    currency_repo = repositories.Currency(session=session)
    await cost_repo.add_cost(candidate)
    await currency_repo.decrease_equity(currency_id, value)
    # auto-commits on context exit
```

**Domain Repositories**: `repositories.Cost` (costs, categories, shortcuts), `repositories.Income`, `repositories.Exchange`, `repositories.Currency` (currencies, equity), `repositories.User`, `repositories.News`, `repositories.Job`, `repositories.ExchangeRate`.

**Query Services**: `TransactionsAnalyticsService` (read-only cross-entity analytics in `infrastructure/query_services/`).

**Data Flow**: HTTP Resources → Application (orchestration) → Infrastructure (repositories) → Database

## Authentication

JWT-based authentication with persistent refresh tokens. Supports backward compatibility with legacy token auth.

**Endpoints** (`/auth`):

- `POST /auth/login` - Authenticate with username/password, returns token pair
- `POST /auth/refresh` - Exchange refresh token for new access token (refresh token reused)
- `POST /auth/logout` - Revoke refresh token

**Token Types**:

- Access token: Short-lived (15 min default), used in `Authorization: Bearer <token>` header
- Refresh token: Long-lived (7 days default), stored hashed in database, remains valid until expiration or logout

**Security**:

- Passwords hashed with Argon2 (OWASP recommended)
- Refresh tokens stored as SHA256 hashes
- Rate limiting on login (5/min, 20/hour) and refresh (10/min) endpoints

**Authorization** (`src/application/authentication.py`):

```python
# FastAPI dependency injection - auto-detects JWT vs legacy token
from src.application.authentication import authorize

@router.get("/protected")
async def protected_route(user: domain.User = Depends(authorize)):
    ...
```

## Configuration

Environment variables prefixed with `FBB__` (nested: `FBB__DATABASE__HOST`). See `src/config/__init__.py` for all settings.

**JWT Settings** (`FBB__JWT__*`):

- `SECRET_KEY` - JWT signing key (change in production)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token lifetime (default: 15)
- `REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token lifetime (default: 7)

**Rate Limit Settings** (`FBB__RATE_LIMIT__*`):

- `LOGIN_PER_MINUTE` / `LOGIN_PER_HOUR` - Login endpoint limits
- `REFRESH_PER_MINUTE` - Token refresh endpoint limit

## Testing

- Tests require running database (`make infra`)
- Use `@pytest.mark.use_db` marker for tests that interact with database
- Fixtures: `john`, `marry` (users), `client` (authorized httpx client), `anonymous` (unauthorized client)
- Factory fixtures: `cost_factory`, `income_factory`, `exchange_factory`, `cost_shortcut_factory`
- pytest-xdist creates isolated test databases per worker
- Suppress logs in tests: `FBB__PYTEST_LOGGING=off`

## Code Style

- Line length: 79 characters
- Python 3.12+
- Type hints required (mypy with pydantic and sqlalchemy plugins)
- `InternalData` base class for domain entities (Pydantic with `from_attributes=True`)

