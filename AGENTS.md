# Repository Guidelines

## Project Structure & Module Organization

This repository contains an HRMS application split into two main workspaces. `app/api/` holds the FastAPI backend, with route handlers in `routers/`, domain logic in `services/`, persistence helpers in `repositories/`, shared utilities in `utils/`, Alembic configuration in `alembic.ini`, and tests in `tests/`. `app/web/` contains the Nuxt frontend, with pages and layouts under `app/`, shared TypeScript types in `shared/types/`, server proxy/auth endpoints in `server/api/`, and static assets in `public/`. Planning and audit notes live in `docs/`.

**Before changing architecture, auth, roles, or any workflow, read `docs/system-architecture-and-flows.md`.** It is the end-to-end reference: layering rules, the permission/scope model, the ERP ownership boundary, per-role UI and API flows, state machines, and a decision register of known gaps. If your change adds or removes a router, permission code, page, or ERP endpoint, update the matching table in that document in the same pull request.

## Build, Test, and Development Commands

Run backend commands from `app/api/`:

```bash
uv sync
uv run fastapi dev main.py
uv run pytest
uv run ruff check .
```

`uv sync` installs Python dependencies from `pyproject.toml` and `uv.lock`. `fastapi dev` starts the API locally, normally at `http://localhost:8000`. `pytest` runs the backend test suite. `ruff check` validates Python style.

Run frontend commands from `app/web/`:

```bash
pnpm install
pnpm dev
pnpm build
pnpm lint
pnpm typecheck
```

`pnpm dev` starts Nuxt locally, usually on `http://localhost:3000`. `build`, `lint`, and `typecheck` should pass before merging frontend changes.

## Coding Style & Naming Conventions

Python uses Ruff with a 120-character line length. Prefer clear snake_case module and function names, async SQLAlchemy/FastAPI patterns already present in the API, and service-layer logic outside routers. TypeScript and Vue use Nuxt conventions: PascalCase components, kebab-case page paths, composables named `useThing.ts`, and shared interfaces in `shared/types/`.

## Testing Guidelines

Backend tests use `pytest` and live in `app/api/tests/` with names like `test_notifications.py` and `test_milestone_6.py`. Add or update tests when changing routers, services, repositories, auth behavior, or migrations. Frontend has linting and type checking configured; add component or end-to-end tests if a test framework is introduced.

## Commit & Pull Request Guidelines

Recent commits use short conventional-style messages such as `feat: Initial pages implemented` and `chore: moved directory`. Follow that pattern with imperative, scoped subjects where possible. Pull requests should include a concise summary, testing performed, linked issues or docs, migration/config notes, and screenshots for visible UI changes.

## Security & Configuration Tips

Keep secrets out of Git. Use `.env.example` as the backend configuration reference and local `.env` files for private values. When touching auth, roles, or session handling, document any required environment changes and run the relevant backend tests before review.
