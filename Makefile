PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PYTHON_BIN := $(BIN)/python
UVICORN := $(BIN)/uvicorn
ALEMBIC := $(BIN)/alembic
APP_MODULE ?= app.main:app
HOST ?= 0.0.0.0
PORT ?= 8000
ENV_FILE ?= app/.env
REQUIREMENTS_FILE ?= app/backend/requirements.txt
ENV_EXAMPLE := $(firstword $(wildcard app/env/.env.example .env.example))
MESSAGE ?= init

.PHONY: help venv install setup env local run dev compile ci clean reset-db docker-build docker-up docker-down docker-logs migration migrate-up migrate-down migrate-current migrate-history migrate-heads

help:
	@echo "Available targets:"
	@echo "  make venv       Create the virtual environment"
	@echo "  make install    Install dependencies from $(REQUIREMENTS_FILE)"
	@echo "  make env        Create $(ENV_FILE) from the example file if missing"
	@echo "  make setup      Prepare venv, dependencies, and env file"
	@echo "  make local      Run uvicorn locally with reload on 0.0.0.0"
	@echo "  make run        Run the FastAPI app"
	@echo "  make dev        Run the FastAPI app with reload"
	@echo "  make compile    Compile-check the app package"
	@echo "  make ci         Run the local CI checks"
	@echo "  make clean      Remove Python cache files"
	@echo "  make reset-db   Remove the local SQLite database"
	@echo "  make docker-build  Build the Docker image"
	@echo "  make docker-up     Start the app with docker compose"
	@echo "  make docker-down   Stop docker compose services"
	@echo "  make docker-logs   Tail docker compose logs"
	@echo "  make migration MESSAGE=\"create users table\"  Autogenerate a new Alembic revision"
	@echo "  make migrate-up    Apply migrations up to head"
	@echo "  make migrate-down  Roll back the latest migration"
	@echo "  make migrate-current  Show the current revision"
	@echo "  make migrate-history  Show migration history"
	@echo "  make migrate-heads    Show current heads"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQUIREMENTS_FILE)

env:
	@if [ -f "$(ENV_FILE)" ]; then \
		echo "$(ENV_FILE) already exists"; \
	elif [ -n "$(ENV_EXAMPLE)" ]; then \
		cp "$(ENV_EXAMPLE)" "$(ENV_FILE)"; \
		echo "Created $(ENV_FILE) from $(ENV_EXAMPLE)"; \
	else \
		echo "No .env example file found"; \
		exit 1; \
	fi

setup: install env

local:
	@if [ -x "$(UVICORN)" ]; then \
		"$(UVICORN)" "$(APP_MODULE)" --host "$(HOST)" --reload; \
	else \
		$(PYTHON) -m uvicorn "$(APP_MODULE)" --host "$(HOST)" --reload; \
	fi

run:
	@if [ -x "$(UVICORN)" ]; then \
		"$(UVICORN)" "$(APP_MODULE)" --host "$(HOST)" --port "$(PORT)"; \
	else \
		$(PYTHON) -m uvicorn "$(APP_MODULE)" --host "$(HOST)" --port "$(PORT)"; \
	fi

dev:
	@if [ -x "$(UVICORN)" ]; then \
		"$(UVICORN)" "$(APP_MODULE)" --reload --host "$(HOST)" --port "$(PORT)"; \
	else \
		$(PYTHON) -m uvicorn "$(APP_MODULE)" --reload --host "$(HOST)" --port "$(PORT)"; \
	fi

compile:
	@if [ -x "$(PYTHON_BIN)" ]; then \
		"$(PYTHON_BIN)" -m compileall app; \
	else \
		$(PYTHON) -m compileall app; \
	fi

ci: install
	@if [ -x "$(PYTHON_BIN)" ]; then \
		"$(PYTHON_BIN)" -m pip check; \
		"$(PYTHON_BIN)" -m compileall app; \
		"$(PYTHON_BIN)" -c "from app.main import app; print(app.title)"; \
	else \
		$(PYTHON) -m pip check; \
		$(PYTHON) -m compileall app; \
		$(PYTHON) -c "from app.main import app; print(app.title)"; \
	fi

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

reset-db:
	rm -f pdf_chatbot.db

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f backend

migration:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" revision --autogenerate -m "$(MESSAGE)"; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic revision --autogenerate -m "$(MESSAGE)"; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi

migrate-up:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" upgrade head; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic upgrade head; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi

migrate-down:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" downgrade -1; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic downgrade -1; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi

migrate-current:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" current; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic current; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi

migrate-history:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" history; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic history; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi

migrate-heads:
	@if [ -x "$(ALEMBIC)" ]; then \
		"$(ALEMBIC)" heads; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic heads; \
	else \
		echo "Alembic command not found. Run 'make install' first."; \
		exit 1; \
	fi
