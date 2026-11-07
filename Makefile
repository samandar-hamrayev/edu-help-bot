.DEFAULT_GOAL := help
PYTHON ?= python3
COMPOSE ?= docker compose

.PHONY: help install lint format test cov migrate makemigrations run-web run-bot up down logs superuser

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime + dev dependencies and git hooks
	$(PYTHON) -m pip install -r requirements-dev.txt
	pre-commit install

lint: ## Run ruff lint and format check
	ruff check .
	ruff format --check .

format: ## Auto-fix lint issues and format code
	ruff check --fix .
	ruff format .

test: ## Run the test suite (needs PostgreSQL, see README)
	pytest

cov: ## Run tests with coverage report
	pytest --cov --cov-report=term-missing

makemigrations: ## Create migrations
	$(PYTHON) manage.py makemigrations

migrate: ## Apply migrations
	$(PYTHON) manage.py migrate

run-web: ## Run Django dev server (admin)
	$(PYTHON) manage.py runserver

run-bot: ## Run the Telegram bot worker
	$(PYTHON) run_bot.py

up: ## Build and start the Docker stack
	$(COMPOSE) up -d --build

down: ## Stop the Docker stack
	$(COMPOSE) down

logs: ## Follow Docker logs
	$(COMPOSE) logs -f --tail=100

superuser: ## Create a Django superuser inside the web container
	$(COMPOSE) exec web python manage.py createsuperuser
