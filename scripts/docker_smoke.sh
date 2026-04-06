#!/usr/bin/env bash
set -euo pipefail

# Docker smoke test — build, start, verify, stop
# Usage: bash scripts/docker_smoke.sh

COMPOSE_FILE="infra/docker-compose.yml"
BASE_URL="http://localhost:8000"
TIMEOUT=60

echo "=== Aurion Docker Smoke Test ==="

# Build and start
echo "[1/5] Building containers..."
docker-compose -f "$COMPOSE_FILE" build --quiet

echo "[2/5] Starting services..."
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for health
echo "[3/5] Waiting for API to become healthy..."
elapsed=0
until curl -sf "$BASE_URL/api/health" > /dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$TIMEOUT" ]; then
        echo "FAIL: API did not become healthy within ${TIMEOUT}s"
        docker-compose -f "$COMPOSE_FILE" logs api
        docker-compose -f "$COMPOSE_FILE" down
        exit 1
    fi
done
echo "  API healthy after ${elapsed}s"

# Run checks
echo "[4/5] Running endpoint checks..."
PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo "  ✓ $name"
        PASS=$((PASS + 1))
    else
        echo "  ✗ $name"
        FAIL=$((FAIL + 1))
    fi
}

check "GET /api/health" "curl -sf $BASE_URL/api/health"
check "GET /api/health/ready" "curl -sf $BASE_URL/api/health/ready"
check "GET /api/metrics" "curl -sf $BASE_URL/api/metrics"
check "GET /api/tickers?query=AAPL" "curl -sf '$BASE_URL/api/tickers?query=AAPL'"
check "POST /api/predict (stat)" "curl -sf -X POST $BASE_URL/api/predict -H 'Content-Type: application/json' -d '{\"symbol\":\"AAPL\",\"asset_type\":\"stock\",\"engine\":\"stat\",\"horizon\":7}'"

# Verify response structure
echo "  Checking response structure..."
RESPONSE=$(curl -sf -X POST "$BASE_URL/api/predict" -H "Content-Type: application/json" -d '{"symbol":"AAPL","asset_type":"stock","engine":"stat","horizon":7}')
echo "$RESPONSE" | python -c "
import sys, json
data = json.load(sys.stdin)
assert 'symbol' in data, 'missing symbol'
assert 'engine_used' in data, 'missing engine_used'
assert 'degraded' in data, 'missing degraded'
assert 'forecast' in data, 'missing forecast'
assert 'summary' in data, 'missing summary'
print('  ✓ Response structure valid')
" || { echo "  ✗ Response structure invalid"; FAIL=$((FAIL + 1)); }

# Cleanup
echo "[5/5] Stopping services..."
docker-compose -f "$COMPOSE_FILE" down

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
