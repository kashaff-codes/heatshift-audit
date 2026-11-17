#!/usr/bin/env bash
# Run the acceptance demo audits once the FortyGuard API is stable.
# Each run waits for 3 consecutive healthy (free) credit-endpoint responses first;
# the CLI itself also pre-flights and stops on the first 5xx submit.
cd "$(dirname "$0")/.." || exit 1
KEY=$(cut -d= -f2 .env)
export PYTHONIOENCODING=utf-8 COLUMNS=150
PY=./.venv/Scripts/python.exe

wait_stable() {
  ok=0
  for i in $(seq 1 150); do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST -H "Content-Type: application/json" \
      -d "{\"api_key\":\"$KEY\"}" https://api.fortyguard.com/v1/system/fetch-api-key-usage)
    echo "$(date -u +%FT%TZ) $code" >> phase_a/outage_probe.log
    if [ "$code" = "200" ]; then ok=$((ok+1)); else ok=0; fi
    [ $ok -ge 3 ] && return 0
    sleep 30
  done
  return 1
}

run() {  # log, then audit args
  log=$1; shift
  for attempt in 1 2 3 4; do
    wait_stable || { echo "API not stable"; return 1; }
    $PY -u -m heatshift audit "$@" --concurrency 1 --yes > "$log" 2>&1
    echo "$log attempt $attempt rc=$?"
    # retry only if something did not complete (failed/skipped/unavailable); completed calls are cached
    grep -qE "looks unavailable|skipped — not submitted|upstream request timeout|Timeout" "$log" || return 0
  done
}

echo "incident seen ~ $(date -u +%FT%TZ)" >> phase_a/outage_probe.log
run runs_houston.log --lat 29.7604 --lon -95.3698 --date 2026-07-15 --name "Houston downtown site" --aoi-side 1000
run runs_miami.log   --lat 25.7617 --lon -80.1918 --date 2026-07-15 --name "Miami downtown site"
run runs_phoenix_cached.log --lat 33.4484 --lon -112.0740 --date 2026-07-15 --name "Phoenix downtown site"
echo DONE
