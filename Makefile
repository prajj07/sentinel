.PHONY: up down logs build test migrate seed ps restart

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

ps:
	docker compose ps

restart:
	docker compose restart

migrate:
	docker compose run --rm migrate

seed:
	docker compose run --rm seed

test:
	docker compose exec -T gateway python -c "print('stack up')" >/dev/null 2>&1 || (echo "Start the stack with 'make up' before running tests" && exit 1)
	pip install -q -r tests/requirements.txt
	pytest -q tests/
