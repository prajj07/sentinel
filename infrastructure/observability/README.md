# Sentinel observability (Sprint 2)

- **Traces:** OpenTelemetry → OTLP → Tempo (`:4317` gRPC, `:3200` HTTP API)
- **Metrics:** Prometheus scrapes `GET /metrics` on each app service (including chaos `:8005`)
- **Dashboards:** Grafana (`:3000`) — provisioned **Sentinel — System Health** board
- **Chaos:** in-process faults tagged with `chaos.experiment_id` on spans

Run `make obs-urls` after `make up`.
