.PHONY: up down logs build test migrate seed ps restart obs-urls chaos-urls chaos-scenario

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

obs-urls:
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3000  (user: admin / password: admin)"
	@echo "Tempo:      http://localhost:3200"
	@echo "RabbitMQ:   http://localhost:15672"

chaos-urls:
	@echo "Chaos engine: http://localhost:8005"
	@echo "  POST /chaos/inject"
	@echo "  POST /chaos/stop/{experiment_id}"
	@echo "  GET  /chaos/experiments"
	@echo "  POST /chaos/scenarios/payment-degradation"

chaos-scenario:
	docker compose run --rm seed
	curl -s -X POST http://localhost:8005/chaos/scenarios/payment-degradation \
	  -H 'Content-Type: application/json' \
	  -d '{"delay_ms":3000,"duration_seconds":30}' | python3 -m json.tool

test:
	docker compose exec -T gateway python -c "print('stack up')" >/dev/null 2>&1 || (echo "Start the stack with 'make up' before running tests" && exit 1)
	docker compose run --rm seed
	pip install -q -r tests/requirements.txt
	pytest -q tests/
