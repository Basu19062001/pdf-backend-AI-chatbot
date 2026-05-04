# PDF Chatbot Backend

Production-style modular monolith backend scaffold for a PDF chatbot system.

## Structure

```text
pdf-chatbot-backend/
├── app/
│   ├── .env
│   ├── backend/
│   │   ├── api/
│   │   └── requirements.txt
│   ├── core/
│   │   └── config.py
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   └── main.py
├── uploads/
├── .github/
├── Makefile
├── docker-compose.yml
└── README.md
```

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/backend/requirements.txt
cp app/env/.env.example app/.env
uvicorn app.main:app --reload
```

Or use `make`:

```bash
make setup
make dev
```

## Docker

```bash
cp app/env/.env.example app/.env
docker compose up --build
```

The Dockerfile lives at `app/Dockerfile`, while `docker-compose.yml` stays at the project root so it can use the whole repository as build context.

Or with `make`:

```bash
make docker-build
make docker-up
```

## CI and Branch Protection

GitHub Actions is the right choice here. The workflow is defined in `.github/workflows/backend-ci.yml` and runs on both:

- pushes to `main` and `development`
- pull requests targeting `main` and `development`

Current CI checks:

- install Python dependencies from `app/backend/requirements.txt`
- validate dependencies with `pip check`
- compile the `app` package
- smoke-test the FastAPI app import

Dependency caching:

- GitHub Actions caches `pip` downloads using `app/backend/requirements.txt` as the cache key source
- Docker now reuses a persistent pip cache during image builds
- local `pip install` also reuses the normal pip cache unless you clear it manually

Run the same checks locally with:

```bash
make ci
```

Important: a workflow alone cannot stop an already completed direct push. To make CI truly block bad code from landing in `main` or `development`, configure GitHub branch protection:

1. Go to `GitHub -> Settings -> Branches`.
2. Add a branch protection rule for `main`.
3. Add another rule for `development`.
4. Enable `Require a pull request before merging`.
5. Enable `Require status checks to pass before merging`.
6. Select the status check named `backend-ci`.
7. Optionally enable `Require approvals` and `Restrict who can push to matching branches`.

Recommended workflow:

- create feature branches from `development`
- open a pull request into `development`
- let CI pass before merge
- promote tested changes from `development` into `main` through another pull request

## Available Endpoints

- `GET /api/v1/health`
- `GET /api/v1/documents/`
- `POST /api/v1/documents/`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/chats/sessions`
- `POST /api/v1/chats/sessions`
- `GET /api/v1/chats/sessions/{session_id}`
- `POST /api/v1/chats/sessions/{session_id}/messages`
- `GET /docs` protected with HTTP Basic auth
- `GET /redoc` protected with HTTP Basic auth
- `GET /openapi.json` protected with HTTP Basic auth

## Docs Security

FastAPI's default public docs are disabled. Documentation endpoints are recreated with HTTP Basic authentication and configured from `app/.env`.

Example variables:

```env
DOCS_ENABLED=true
DOCS_USERNAME=admin
DOCS_PASSWORD=change-this-password
DOCS_URL=/docs
REDOC_URL=/redoc
OPENAPI_URL=/openapi.json
```

## Notes

- The current implementation focuses on production-grade structure and separation of concerns.
- Service implementations for PDF parsing, embeddings, vector storage, and LLM responses are intentionally stubbed and ready to be replaced with real integrations.
- SQLite is the default local database for quick startup, but the app structure is ready for a stronger production database setup.
