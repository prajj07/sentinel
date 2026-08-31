#!/usr/bin/env bash
set -euo pipefail

CHAOS_URL="${CHAOS_URL:-http://localhost:8005}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"

echo "==> Injecting 1.5s payment latency"
INJECT=$(curl -sf -X POST "${CHAOS_URL}/chaos/inject" \
  -H 'Content-Type: application/json' \
  -d '{"service":"payments","type":"latency","duration_seconds":20,"delay_ms":1500}')
echo "${INJECT}"

EXPERIMENT_ID=$(echo "${INJECT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['experiment_id'])")

echo ""
echo "==> POST /orders while chaos is active"
START=$(python3 -c "import time; print(time.time())")
curl -sf -X POST "${GATEWAY_URL}/orders" \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"chaos_verify","items":[{"product_id":"prod_001","quantity":1}],"amount":100}'
echo ""
python3 -c "import time; start=float('${START}'); print(f'elapsed={time.time()-start:.2f}s')"

echo ""
echo "==> Stopping experiment ${EXPERIMENT_ID}"
curl -sf -X POST "${CHAOS_URL}/chaos/stop/${EXPERIMENT_ID}"
echo ""

echo ""
echo "==> Experiment history"
curl -sf "${CHAOS_URL}/chaos/experiments" | python3 -m json.tool | head -40
