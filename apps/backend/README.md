# Truvix Backend

FastAPI service behind the Truvix vehicle intelligence app: accounts, the
garage, analysis runs, the AI copilot and the notification centre.

## Architecture

A modular monolith. Each feature lives under `src/truvix/modules/<name>/` and
owns its models, schemas, repository, service and router. Modules depend on the
shared kernel (`src/truvix/shared/`) and on each other's public interfaces, not
on each other's tables.

| Layer | Responsibility |
| --- | --- |
| `router.py` | HTTP shape only: parse, delegate, serialise |
| `service.py` | Business rules and invariants |
| `repository.py` | The only place that builds queries for the module |
| `models.py` | SQLAlchemy mappings and database constraints |
| `schemas.py` | Pydantic request and response contracts |

Two rules hold everywhere and are worth stating plainly:

- **Every read is scoped to its owner.** Repository methods take the user id
  and filter on it, so a handler cannot accidentally fetch by identifier alone
  and serve one account's data to another.
- **Missing and forbidden are the same answer.** A record belonging to someone
  else returns 404, never 403, so the API cannot confirm that it exists.

Modules communicate through domain events (`shared/events.py`) when a change in
one has consequences in another. Events are dispatched inside the request's
transaction, so a price drop and the notification it produces commit together
or not at all.

## Requirements

- Python 3.14 (`uuid.uuid7` gives time-ordered primary keys, keeping inserts
  index-local)
- PostgreSQL 18
- Redis 7

## Running locally

```bash
cp .env.example .env          # then set TRUVIX_SECURITY_SECRET_KEY
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run uvicorn truvix.main:app --reload
```

The API is then at `http://localhost:8000`, with interactive documentation at
`/docs` (disabled automatically in staging and production).

### With Docker

```bash
docker compose run --rm migrate
docker compose up backend
```

`migrate` runs to completion and exits before the API starts, so the service
never comes up against a schema it does not expect.

## Configuration

Every setting is declared in `shared/config/settings.py` and read from the
environment with a `TRUVIX_` prefix; no module reads `os.environ` directly. The
configuration is validated once at import, so a misconfigured deployment fails
at startup with a precise message instead of failing obscurely hours later.

Production-like environments additionally reject a default signing key and a
wildcard host allowlist.

AI is optional. Without `TRUVIX_AI_API_KEY` the copilot reports itself
unavailable and analyses fall back to the deterministic rule engine; nothing
else changes.

With a key configured, an analysis additionally has its photographs inspected
by a vision model, and the findings that produces feed the reasoning step. Each
image is reduced to a bounded size server-side before it is sent, so the cost
of an analysis does not depend on which handset took the picture, and at most
six are sent per run. Every stage degrades independently: a failed inspection
still produces a report, and a failed reasoning step still keeps the visual
findings.

## Subscriptions

Premium is sold through In-App Purchase, because Apple's review guideline 3.1.1
requires it for digital content consumed inside the app — billing it through a
payment provider instead is grounds for rejection.

The app sends the signed transaction StoreKit gave it to
`POST /api/v1/subscriptions/redeem`, and nothing about it is trusted until
three things hold:

1. its certificate chain terminates at a root in
   `TRUVIX_SUBSCRIPTION_APPLE_ROOT_CERTIFICATE_DIR`, compared by fingerprint
   rather than by subject, since a subject line can be copied into any
   self-signed certificate;
2. the signature over the payload verifies, so it was not edited afterwards;
3. the payload names this bundle, so a genuine Apple transaction issued for
   another application cannot be redeemed here.

Sandbox transactions are refused unless `TRUVIX_SUBSCRIPTION_ALLOW_SANDBOX` is
set, and production configuration rejects that flag at startup: a sandbox
purchase is free yet carries the same Apple signature as a real one, so the
environment claim is the only thing separating a paying customer from anyone
with a free test account.

Set the App Store server notification URL to
`POST /api/v1/subscriptions/notifications`. Refunds and cancellations arrive
only that way — the app may not be running when they happen — so without it a
refunded customer keeps premium until their paid term expires. The endpoint
takes no token, because Apple cannot hold one; the envelope's signature is what
authenticates it, and the transaction nested inside is verified separately.

The account's tier is recomputed from its entitlements rather than toggled, so
a lapsed subscription cannot leave an account premium because one code path
forgot to unset it. `bundle_id` unset disables the endpoints altogether: they
refuse every transaction rather than accept one nobody can check.

## Testing

```bash
uv run pytest                    # everything
uv run pytest -m "not integration"   # unit tests only, no services needed
```

Integration tests run against a real PostgreSQL and Redis. They are not
optional extras: two security defects — a lockout counter and a token-reuse
revocation, both silently rolled back with the failing request that triggered
them — were invisible to unit tests and only surfaced here.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Autogenerated scripts need review before they are committed. In particular,
dropping a table does not drop its PostgreSQL enum types, so every migration
that creates enums drops them again in `downgrade()`. CI runs the full
`upgrade → downgrade → upgrade` cycle: a migration that cannot be undone is a
migration that cannot be rolled back in production.

## API schema

`docs/openapi.json` is generated, not hand-maintained:

```bash
uv run python scripts/export_openapi.py
```

CI fails if the committed file differs from what the code produces.

## Quality gates

CI runs formatting, linting, `mypy --strict`, the full test suite against real
services, the migration reversibility cycle, the schema drift check, and a
container build that must report itself alive. All of them must pass.
