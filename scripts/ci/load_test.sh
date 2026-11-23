#!/usr/bin/env bash
# Locust load test around a deployment (staging and production).
#
#   scripts/ci/load_test.sh start <env> <url>          20 users in the background (LOCUST_WEB_PASSWORD to log in)
#   scripts/ci/load_test.sh stop  <env> <tag> <min_s>  keep it on for at least <min_s> seconds, stop, judge
#   scripts/ci/load_test.sh abort                      stop without judging (failed deployment)
#
# Verdict: any failed request (5xx, refused or reset connection) or no request at all fails;
# a 95th percentile above 2 s only warns, because the network between GitHub and AWS varies.
# Writes a "Load test" table to the job summary; the workflow uploads locust-out/ as the
# artifact locust-<env>-<tag>.
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ci/lib.sh
source scripts/ci/lib.sh

OUT=locust-out
USERS=20
P95_LIMIT_MS=2000

stop_locust() {
  [ -f "$OUT/pid" ] || return 0
  local pid
  pid=$(cat "$OUT/pid")
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" # Locust quits cleanly on SIGTERM and writes its CSV files
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$OUT/pid"
}

case "${1:-}" in
  start)
    ENV_NAME="$2" URL="$3"
    rm -rf "$OUT"
    mkdir -p "$OUT"
    nohup locust -f tests/load/locustfile.py --headless --users "$USERS" --spawn-rate 5 --run-time 60m \
      --host "$URL" --csv "$OUT/locust" --html "$OUT/report.html" --only-summary --stop-timeout 10 \
      >"$OUT/locust.log" 2>&1 &
    echo $! >"$OUT/pid"
    date +%s >"$OUT/started"
    sleep 5
    kill -0 "$(cat "$OUT/pid")" 2>/dev/null || {
      cat "$OUT/locust.log"
      fail "Locust did not start"
    }
    log "load test started: $USERS users against $URL ($ENV_NAME)"
    ;;

  stop)
    ENV_NAME="$2" TAG="$3" MIN_SECONDS="$4"
    [ -f "$OUT/pid" ] || fail "no load test is running"
    elapsed=$(($(date +%s) - $(cat "$OUT/started")))
    if [ "$elapsed" -lt "$MIN_SECONDS" ]; then
      log "load test has run ${elapsed}s; keeping it on until ${MIN_SECONDS}s"
      sleep $((MIN_SECONDS - elapsed))
    fi
    stop_locust
    duration=$(($(date +%s) - $(cat "$OUT/started")))
    [ -f "$OUT/locust_stats.csv" ] || {
      cat "$OUT/locust.log"
      fail "Locust wrote no statistics"
    }
    python3 - "$OUT" "$ENV_NAME" "$TAG" "$duration" "$USERS" "$P95_LIMIT_MS" <<'PY'
import csv, os, sys

out, env, tag, duration, users, limit = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5], int(sys.argv[6])
rows = list(csv.DictReader(open(f"{out}/locust_stats.csv", encoding="utf-8")))
total = next(r for r in rows if r["Name"] == "Aggregated")
requests, failures = int(total["Request Count"]), int(total["Failure Count"])
p95 = float(total["95%"] or 0)
lines = [
    f"### Load test: {env} `{tag}`", "",
    f"{users} users for {duration} s, from before the rolling update until after the smoke test.", "",
    "| Endpoint | Requests | Failures | Median ms | p95 ms | Max ms |", "|---|---:|---:|---:|---:|---:|",
]
for r in rows:
    name = "**All**" if r["Name"] == "Aggregated" else f"{r['Type']} {r['Name']}"
    lines.append(f"| {name} | {r['Request Count']} | {r['Failure Count']} | {r['50%']} | {r['95%']} | {float(r['Max Response Time']):.0f} |")
failure_file = f"{out}/locust_failures.csv"
if failures and os.path.exists(failure_file):
    lines += ["", "| Failed request | Error | Count |", "|---|---|---:|"]
    for r in csv.DictReader(open(failure_file, encoding="utf-8")):
        lines.append(f"| {r['Method']} {r['Name']} | {r['Error'][:120]} | {r['Occurrences']} |")
verdict, code = "passed", 0
if requests == 0:
    verdict, code = "failed: no request was sent", 1
elif failures:
    verdict, code = f"failed: {failures} of {requests} requests failed", 1
elif p95 > limit:
    verdict = f"passed with a warning: p95 {p95:.0f} ms is above {limit} ms"
    print(f"::warning::{env} load test p95 {p95:.0f} ms is above {limit} ms")
lines += ["", f"**Verdict: {verdict}**", ""]
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    open(summary, "a", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(code)
PY
    ;;

  abort)
    stop_locust
    ;;

  *)
    fail "usage: load_test.sh start|stop|abort ..."
    ;;
esac
