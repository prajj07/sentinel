from prometheus_client import Counter, Gauge

CHAOS_INJECTIONS = Counter(
    "chaos_injections_total",
    "Chaos fault activations on this process",
    ["service", "type"],
)
CHAOS_REQUESTS_AFFECTED = Counter(
    "chaos_requests_affected_total",
    "HTTP requests that were delayed or failed by chaos",
    ["service", "type"],
)
CHAOS_ACTIVE_EXPERIMENTS = Gauge(
    "chaos_active_experiments",
    "Whether a chaos experiment is currently active (0 or 1)",
    ["service"],
)
