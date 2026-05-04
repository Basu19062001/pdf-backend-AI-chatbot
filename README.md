# PDF Chatbot Backend

Production-style modular monolith backend scaffold for a PDF chatbot system.

## Structure

```text
pdf-chatbot-backend/
├── app/
│   ├── api/
│   │   ├── dependencies.py
│   │   ├── router.py
│   │   └── routes/
│   ├── core/
│   │   └── config.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── utils/
│   └── main.py
├── uploads/
├── .env.example
├── requirements.txt
└── README.md
```

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Or use `make`:

```bash
make setup
make dev
```

## Available Endpoints

- `GET /api/v1/health`
- `GET /api/v1/documents/`
- `POST /api/v1/documents/`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/chats/sessions`
- `POST /api/v1/chats/sessions`
- `GET /api/v1/chats/sessions/{session_id}`
- `POST /api/v1/chats/sessions/{session_id}/messages`

## Notes

- The current implementation focuses on production-grade structure and separation of concerns.
- Service implementations for PDF parsing, embeddings, vector storage, and LLM responses are intentionally stubbed and ready to be replaced with real integrations.
- SQLite is the default local database for quick startup, but the app structure is ready for a stronger production database setup.
