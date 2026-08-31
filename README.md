# Sentinel

Autonomous production reliability platform — Sprints 1–3: a real local distributed system with traces, metrics, and a chaos engine that can break it on purpose.

## Architecture

```text
Client
  │
  ▼
Gateway (:8000)
  │
  ▼
Orders (:8001)
  ├── Inventory (:8002) ── Redis + PostgreSQL
  └── Payments (:8003) ── PostgreSQL
  │
  ▼
RabbitMQ ──► Notifications (:8004)

Chaos Engine (:8005) ── inject/stop ──► gateway / orders / inventory / payments
```

- **Sync path:** Client → Gateway → Orders → Inventory + Payments
- **Async path:** Orders publishes `order.created` → RabbitMQ → Notifications consumer
- Gateway does **not** call Inventory or Payments directly

## Services

| Service | Port | Responsibility |
|---------|------|----------------|
| gateway | 8000 | Routing + request validation |
| orders | 8001 | Order workflow ownership |
| inventory | 8002 | Stock lookup/reserve + Redis cache |
| payments | 8003 | Simulated payments (SUCCESS / FAILED) |
| notifications | 8004 | Consumes `order.created` |
| chaos | 8005 | Experiment control plane (dev only) |

Infrastructure: PostgreSQL (`5432`), Redis (`6379`), RabbitMQ (`5672` / management `15672`).

## Local setup

Requirements: Docker + Docker Compose.

```bash
cp .env.example .env   # optional; Compose has defaults
make up                # docker compose up -d --build
make ps                # verify healthy
```

Migrations and inventory seed run automatically via `migrate` and `seed` services.

## Environment variables

See [`.env.example`](.env.example). Key values:

- `DATABASE_URL` — SQLAlchemy URL for shared `sentinel` DB
- `REDIS_URL` — inventory cache
- `RABBITMQ_URL` / `RABBITMQ_EXCHANGE` — messaging
- `ORDERS_URL`, `INVENTORY_URL`, `PAYMENTS_URL` — service DNS URLs
- `HTTP_TIMEOUT_SECONDS`, `GATEWAY_HTTP_TIMEOUT_SECONDS`

Do not commit real secrets.

## API endpoints

| Method | Path | Service |
|--------|------|---------|
| GET | `/health` | all |
| POST | `/orders` | gateway, orders |
| GET | `/inventory/{product_id}` | inventory |
| POST | `/inventory/reserve` | inventory |
| POST | `/inventory/release` | inventory (compensating restore) |
| POST | `/payments` | payments (always SUCCESS) |
| POST | `/payments/simulate-failure` | payments (FAILED; test/dev only) |
| GET | `/notifications/received` | notifications (debug) |
| DELETE | `/notifications/received` | notifications (debug) |
| GET | `/metrics` | all |
| POST | `/chaos/inject` | chaos |
| POST | `/chaos/stop/{experiment_id}` | chaos |
| GET | `/chaos/experiments` | chaos |
| POST | `/chaos/scenarios/payment-degradation` | chaos |

### Create order example

```bash
curl -s http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{
    "customer_id": "cust_001",
    "items": [{"product_id": "prod_001", "quantity": 2}],
    "amount": 1499
  }'
```

## How services communicate

1. Gateway validates `CreateOrderRequest` and forwards to Orders over HTTP (timeout enforced).
2. Orders inserts an order (`pending`), reserves inventory, charges payment, updates status (`reserved` → `confirmed` or `failed`).
3. If payment fails (or a later reserve fails) after inventory was reserved, Orders calls `/inventory/release` to restore stock.
4. On confirmation, Orders publishes `order.created` to exchange `sentinel.events`.
5. Notifications consumes queue `order.created` and records the event in memory.

Inventory GET is a read-through Redis cache (TTL 60s by default) backed by PostgreSQL. Reserve uses `SELECT … FOR UPDATE` and refreshes the cache. Release is the compensating inverse of reserve.

Optional request field `simulate_payment_failure: true` (test/dev) makes Orders call `/payments/simulate-failure` so compensation can be exercised end-to-end. Idempotent order creation is not implemented yet.

## Make targets

```bash
make up       # build + start full stack
make down     # stop
make logs     # follow logs
make build    # build images
make migrate  # run Alembic
make seed     # seed inventory
make test     # integration tests (stack must be up)
make ps       # container status
make obs-urls # Prometheus / Grafana / Tempo URLs
make chaos-urls
make chaos-scenario  # run payment-degradation experiment
```

## Observability (Sprint 2)

Every service exports:

- **Traces** → Tempo via OpenTelemetry (W3C `traceparent` across HTTP + RabbitMQ)
- **Metrics** → `GET /metrics` (Prometheus format)

| UI | URL | Default login |
|----|-----|----------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| Tempo API | http://localhost:3200 | — |

### Verify trace propagation

```bash
# Happy path order + search Tempo for linked trace
bash scripts/verify_trace.sh

# Or manually
curl -s -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"cust_001","items":[{"product_id":"prod_001","quantity":1}],"amount":100}'

# Grafana → Explore → Tempo → search service.name=gateway
```

### Key metrics

| Metric | Service |
|--------|---------|
| `orders_created_total`, `orders_failed_total`, `order_duration_seconds` | orders |
| `payments_total`, `payments_failed_total`, `payment_duration_seconds` | payments |
| `inventory_reservations_total`, `inventory_releases_total` | inventory |
| `http_requests_total`, `http_request_duration_seconds` | all |

## Tests

With the stack running:

```bash
make test
```

Covers health checks, Redis cache, compensation, observability (`tests/test_observability.py`), chaos (`tests/test_chaos.py`), and the full order flow.

## Chaos engineering (Sprint 3)

The chaos engine injects **in-process** faults (latency, HTTP 500, 503). It does not kill containers or run shell commands. `/health`, `/metrics`, and `/internal/chaos/*` are never faulted so Compose healthchecks stay green.

Control API (`:8005`, local/dev only — do not expose publicly):

| Method | Path |
|--------|------|
| POST | `/chaos/inject` |
| POST | `/chaos/stop/{experiment_id}` |
| GET | `/chaos/experiments` |
| GET | `/chaos/experiments/{experiment_id}` |
| POST | `/chaos/scenarios/payment-degradation` |

```bash
# Inject 3s payment latency for 30s
curl -s -X POST http://localhost:8005/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service":"payments","type":"latency","duration_seconds":30,"delay_ms":3000}'

# Stop
curl -s -X POST http://localhost:8005/chaos/stop/exp_xxxxxxxx

# Automated experiment + report
make chaos-scenario
bash scripts/verify_chaos.sh
```

Fault types: `latency`, `http_500`, `service_unavailable`. Target services: `gateway`, `orders`, `inventory`, `payments`.

Affected requests get span attributes `chaos.experiment_id` and `chaos.failure_type` so Tempo can distinguish **intentional** breakage from unexpected incidents.

## Out of scope (current)

Idempotency keys, AI incident commander, Kubernetes, AWS, Loki/log aggregation, Control Room UI.

## RabbitMQ topology

- Exchange: `sentinel.events` (topic)
- Queues + routing keys: `order.created`, `payment.completed`, `payment.failed`
- Sprint 1 runtime publish/consume: `order.created` only

## Database schema

- `orders(id, customer_id, status, amount, payment_id → payments.id, created_at)`
- `payments(id, order_id → orders.id, status, amount, created_at)`
- `inventory(id, product_id UNIQUE, available_quantity, updated_at)`

Schema is applied with Alembic (no `create_all()` at runtime).
