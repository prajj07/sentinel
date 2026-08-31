#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
TEMPO_URL="${TEMPO_URL:-http://localhost:3200}"

echo "==> POST /orders (happy path)"
ORDER_RESPONSE=$(curl -sf -X POST "${GATEWAY_URL}/orders" \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"trace_verify","items":[{"product_id":"prod_001","quantity":1}],"amount":100}')
echo "${ORDER_RESPONSE}"

echo ""
echo "==> Waiting for traces to land in Tempo..."
sleep 5

echo "==> Searching Tempo for POST /orders traces"
SEARCH=$(curl -sf "${TEMPO_URL}/api/search?tags=service.name%3Dgateway&limit=20")
TRACE_ID=$(echo "${SEARCH}" | python3 -c "
import sys, json
for trace in json.load(sys.stdin).get('traces', []):
    if trace.get('rootTraceName') == 'POST /orders':
        print(trace['traceID'])
        break
" 2>/dev/null || true)
if [[ -z "${TRACE_ID}" ]]; then
  echo "WARN: no trace found yet — check Tempo and retry"
  exit 1
fi

echo ""
echo "==> Fetching trace ${TRACE_ID}"
curl -sf "${TEMPO_URL}/api/traces/${TRACE_ID}" | python3 -m json.tool | head -80

echo ""
echo "Open Grafana -> Explore -> Tempo and search trace ID: ${TRACE_ID}"
