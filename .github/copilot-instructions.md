# Copilot Instructions — FastAPI Service

Build production FastAPI APIs for NLRC 510. Follow these conventions exactly. They are the
consolidated 510 best practices; deviate only with a documented reason.

## Working with the Engineer (Responsible AI Use)

Follow these principles: you assist, the human decides, reviews, and owns the output.

- **Think with the engineer, not for them.** Before generating non-trivial code, briefly discuss the
  approach and trade-offs. Surface design decisions rather than silently picking one.
- **Ask clarifying questions.** If a request is ambiguous, under-specified, or looks like the wrong
  approach, ask first — do not guess and produce a large answer. A short question beats a long wrong
  implementation.
- **Protect the engineer's understanding.** Don't just hand over answers to questions the engineer can
  reason through. Prompt them to attempt it, explain *why* a solution works, and call out edge cases.
  Optimize for long-term comprehension over speed.
- **Don't reinvent the wheel.** Prefer well-maintained existing libraries over bespoke implementations.
  Before writing custom code for a common problem (parsing, retries, validation, HTTP, dates), check
  whether the stdlib or an already-used dependency solves it, and say why a library is better.
- **Small, reviewable changes.** Keep diffs focused; separate refactors from features. Never produce
  massive, opaque changes.
- **Be transparent.** AI-assisted contributions should be disclosed (e.g. commit trailers) and must be
  fully understood by the human who commits them.
- **No secrets or PII into prompts/tools.** Never paste beneficiary, donor, or personnel data into AI
  tooling. Treat all generated code as untrusted until reviewed.

## Stack & Tooling

- **Python 3.12+**, managed with **uv** (never pip/poetry/virtualenv).
- Lint/format with **ruff**; type-check with **ty** (fallback **mypy**).
- Test with **pytest** + `TestClient` (requires `httpx`).
- Run production with **gunicorn + UvicornWorker**; deploy as a **Docker** image.
- License: **Apache-2.0**. Built by [NLRC 510](https://www.510.global/).

```bash
uv sync                 # install (incl. dev)
uv add fastapi          # add runtime dep
uv add --dev pytest     # add dev dep
uv run pytest           # test
uv run ruff check .     # lint
uv run ty check         # type check
```

## Project Structure

Use a layered `src/` layout. Enforce import boundaries with `import-linter`
(`api → services → domain`; `domain` imports nothing from the project; `adapters` implement `domain` ports).

```
src/my_app/
├── main.py              # uvicorn entry: app = create_app()
├── settings.py          # pydantic-settings AppSettings
├── domain/              # pure business logic (no framework imports)
│   ├── models.py        # frozen dataclasses / Pydantic
│   ├── errors.py        # DomainError hierarchy
│   └── ports.py         # Protocol/ABC interfaces
├── services/            # use-case orchestration (imports domain only)
├── adapters/            # external integrations (db, llm, http)
└── api/
    ├── app.py           # create_app() factory
    ├── routes.py        # APIRouter handlers
    ├── schemas.py       # request/response Pydantic models
    ├── dependencies.py  # Depends() functions
    └── log.py           # setup_logging()
tests/{domain,services,adapters,api,integration,e2e}/  # mirror src; conftest.py per layer
```

For tiny services (≤5 endpoints) a flat `main.py` + `routes/` + `utils/` is acceptable; graduate to the
layered layout as it grows.

## Application Setup

- Always use a **`create_app()` factory** (composition root) over a module-level `app`.
- Build expensive resources in an **async `lifespan`** context manager (not `@app.on_event`) and store
  them on `app.state`. Access via `Depends` reading `request.app.state`.
- **No module-level singletons** for external clients — inject via factory or lifespan.
- Add middleware in the factory (request-ID, request-logging). Register exception handlers there too.
- Always set OpenAPI metadata: `title`, `version`, `description`, `license_info` (Apache-2.0), tags.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = AppSettings()
    app.state.orchestrator = build_orchestrator(settings)
    yield
    await app.state.db.dispose()

def create_app() -> FastAPI:
    app = FastAPI(title="my-app", version=__version__, lifespan=lifespan,
                  license_info={"name": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"})
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(router, prefix="/v1")
    register_exception_handlers(app)
    return app
```

## Routes & Schemas

- Use `APIRouter` with `tags` and version `prefix`. Route functions use verb-noun names.
- **Always define explicit Pydantic request/response schemas** in `api/schemas.py`; never accept/return raw
  `dict` or `Request.json()`. Declare `response_model` and explicit `status_code`.
- Keep handlers **thin**: validate input → call service → map result. Map between API schemas and domain
  models explicitly in the handler.
- Inject services and auth via `Depends`. Use `Path`/`Query`/`Body` with validation (`ge`, `le`, `Field`).

## Configuration

- Centralize all config in **`pydantic-settings`** `BaseSettings` classes. **Never scatter `os.environ`.**
- Group by concern with `env_prefix` (`LLM_`, `DB_`, `AUTH_`). Required fields have no default → fail fast.
- Wrap secrets in **`SecretStr`**. Load `.env` locally (gitignored); use Azure Key Vault in production.
- Provide a committed `example.env` with comments. Compose a single root `AppSettings`, instantiate once.

## Error Handling

- Define an HTTP-independent **`DomainError`** hierarchy in `domain/errors.py`
  (`AuthenticationError`, `AuthorizationError`, `NotFoundError`, `ValidationError`, `ExternalServiceError`…).
- Adapters **translate** external exceptions to domain errors (`raise ... from e`).
- Register global exception handlers mapping domain errors → consistent JSON:
  `{"error": {"code", "message", "request_id"}}`. Catch-all → 500 with generic message (never leak internals).
- Never use bare `except:`; catch specific exceptions. Log errors at the handler boundary.

## Authentication

- API-key services: `APIKeyHeader` + `secrets.compare_digest` (constant-time). Separate read vs write keys
  via dependencies. Multi-tenant: `HTTPBearer` matching against keys loaded into `app.state`.
- Use `dependency_overrides` for testing — never `test_mode` flags in production code.
- Never log credentials; store keys as `SecretStr`; source from Key Vault in production.

## Testing

- Mirror `src/` layers under `tests/`. Mark slow tiers with `@pytest.mark.integration` / `e2e`.
- **Use `TestClient` as a context manager** so `lifespan` runs and `app.state` is initialized.
- Isolate env in `conftest.py` (strip `LLM_`, `DB_`, `AUTH_`… vars) for deterministic tests.
- Larger apps: build via `create_app(...)` with fake factories; inject fakes through `app.state` /
  `dependency_overrides`. Patch externals where they are *used*.

```python
uv run pytest --cov=src --cov-report=term-missing
uv run pytest -m "not integration"
```

## Logging & Observability

- One logger per module (`logging.getLogger(__name__)`). Configure once in `setup_logging()` (called in
  lifespan). Default INFO; DEBUG only in development. Silence noisy libs (`httpx`, `azure`, `uvicorn.access`).
- Log structured fields via `extra=`, never f-string interpolation of data. **Never log secrets/PII/bodies.**
- Request-logging middleware logs method, path, status, duration_ms, request_id; skip `/health`, `/ready`.
- Production telemetry: **`azure-monitor-opentelemetry`** via `configure_azure_monitor()` (gated on
  `APPLICATIONINSIGHTS_CONNECTION_STRING`). Do **not** use the deprecated `opencensus` packages.
- Expose `GET /health` → `{"status": "ok"}` (untracked in logs).

## Docker & Deployment

Layer deps before code; `--no-dev --frozen --no-editable`; never copy `.env` or `tests/`; add a `.dockerignore`.

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-editable --no-dev --frozen
COPY src/ src/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD [".venv/bin/gunicorn", "my_app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
```

- **Never run `uvicorn.run()` in production** — always gunicorn + UvicornWorker.
- Bind to Azure's injected `PORT`. Use an `entrypoint.sh` only when pre-start tasks (migrations) are needed.

## CI/CD (GitHub Actions)

- `lint-and-test` on push/PR: `uv sync` → `ruff check` → `ruff format --check` → `ty check` →
  `pytest --cov`. Pin actions to major versions.
- Deploy FastAPI as a **Docker image** to GHCR/ACR with `cache-from/to: type=gha`, then
  `azure/webapps-deploy`. Authenticate with **Azure OIDC**. Protect `main`; use GitHub Environments.

## pyproject.toml essentials

```toml
[project]
requires-python = ">=3.12"
dependencies = ["fastapi", "uvicorn", "gunicorn", "pydantic-settings", "httpx", "python-dotenv"]

[dependency-groups]
dev = ["pytest>=8.0", "pytest-cov>=6.0", "httpx>=0.27", "ruff>=0.8", "ty", "import-linter"]

[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E","W","F","I","UP","B","SIM","T20","N","RET","PTH"]
```

Direct deps may stay unpinned (lockfile is source of truth); **always commit `uv.lock`**. On OneDrive set
`UV_LINK_MODE=copy`.

## Anti-Patterns

- Module-level `app = FastAPI()` for non-trivial apps
- Scattered `os.environ`
- Raw `dict` request/response
- Fat handlers with business logic
- `test_mode` flags
- `print()` (use logging)
- Bare `except`
- Logging secrets
- Running uvicorn directly in prod
- Copying `.env`/`tests/` into images
- Hand-rolled auth/validation/retry logic where `fastapi`/`pydantic`/`httpx`/`tenacity` already solve it