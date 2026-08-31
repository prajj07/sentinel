# Sentinel observability (Sprint 2)

- **Traces:** OpenTelemetry → OTLP → Tempo (`:4317` gRPC, `:3200` HTTP API)
- **Metrics:** Prometheus scrapes `GET /metrics` on each app service
- **Dashboards:** Grafana (`:3000`) — provisioned **Sentinel — System Health** board

Run `make obs-urls` after `make up`.
