#!/usr/bin/env bash
set -euo pipefail
MODE=${1:?usage: network_scenario.sh noqos|qos}
[ "$MODE" = noqos ] || [ "$MODE" = qos ] || { echo "mode invalide" >&2; exit 2; }
OUT=/experiments/results_docker
mkdir -p "$OUT"

if [ "$MODE" = qos ]; then
  curl -fsS -H 'Content-Type: application/json' -d '{"busy":20}' http://127.0.0.1:8080/metrics | jq -e '.priority == true' >/dev/null
else
  curl -fsS http://127.0.0.1:8080/health | jq -e '.priority_enabled == false' >/dev/null
fi

ip netns exec edge iperf -s -u -p 9999 -i 1 >"$OUT/ctrl_server_${MODE}.log" 2>&1 & p1=$!
ip netns exec edge iperf -s -u -p 5001 -i 1 >/dev/null 2>&1 & p2=$!
ip netns exec edge iperf -s -u -p 5002 -i 1 >/dev/null 2>&1 & p3=$!
trap 'kill $p1 $p2 $p3 2>/dev/null || true' EXIT
sleep 1
ip netns exec car2 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 8 >/dev/null 2>&1 & c2=$!
ip netns exec car3 iperf -c 10.0.0.254 -u -p 5002 -b 8M -t 8 >/dev/null 2>&1 & c3=$!
ip netns exec car1 iperf -c 10.0.0.254 -u -p 9999 -b 1M -t 8 -i 1 >"$OUT/ctrl_client_${MODE}.log" 2>&1 || true
wait "$c2" "$c3" || true
kill "$p1" "$p2" "$p3" 2>/dev/null || true
wait "$p1" "$p2" "$p3" 2>/dev/null || true
trap - EXIT
python tools/analyze_iperf.py --log "$OUT/ctrl_client_${MODE}.log" --out "$OUT/ctrl_${MODE}.json" --csv "$OUT/ctrl_${MODE}.csv"
jq -e '.summary.samples > 0' "$OUT/ctrl_${MODE}.json" >/dev/null
echo "[SUCCES] scenario reseau $MODE -> $OUT/ctrl_${MODE}.json"
