PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PIP := $(BIN)/pip
PYTHON_BIN := $(BIN)/python
UVICORN := $(BIN)/uvicorn
APP_MODULE ?= app.main:app
HOST ?= 0.0.0.0
PORT ?= 8000
ENV_FILE ?= .env
ENV_EXAMPLE := $(firstword $(wildcard .env.example app/env/.env.example))

.PHONY: help venv install setup env run dev compile clean reset-db docker-build docker-up docker-down docker-logs

help:
	@echo "Available targets:"
	@echo "  make venv       Create the virtual environment"
	@echo "  make install    Install dependencies into the virtual environment"
	@echo "  make env        Create $(ENV_FILE) from the example file if missing"
	@echo "  make setup      Prepare venv, dependencies, and env file"
	@echo "  make run        Run the FastAPI app"
	@echo "  make dev        Run the FastAPI app with reload"
	@echo "  make compile    Compile-check the app package"
	@echo "  make clean      Remove Python cache files"
	@echo "  make reset-db   Remove the local SQLite database"
	@echo "  make docker-build  Build the Docker image"
	@echo "  make docker-up     Start the app with docker compose"
	@echo "  make docker-down   Stop docker compose services"
	@echo "  make docker-logs   Tail docker compose logs"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

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
