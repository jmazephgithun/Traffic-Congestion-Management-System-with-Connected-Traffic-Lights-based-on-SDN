#!/usr/bin/env bash
set -euo pipefail
OUT=/experiments/results_docker
mkdir -p "$OUT"
sumo -c sumo_one_junction/one_junction_asymmetric.sumocfg --remote-port 8813 --seed 42 \
  --time-to-teleport -1 --tripinfo-output "$OUT/tripinfo_closed_loop.xml" >"$OUT/sumo_closed_loop.log" 2>&1 &
sumo_pid=$!
trap 'kill $sumo_pid 2>/dev/null || true' EXIT
sleep 1
python pyfilesTrue/tls_orchestrator_CORRECTED.py --sumo-port 8813 --tls-id J1 \
  --ns-phase-idx 0 --ew-phase-idx 2 --min-green 10 --max-green 45 --hysteresis .15 \
  --post-url http://127.0.0.1:8080/metrics >"$OUT/orchestrator_closed_loop.log" 2>&1
wait "$sumo_pid"
trap - EXIT
grep -q 'Installed priority rule' "$OUT/ryu.log"
grep -q 'Switch ->' "$OUT/orchestrator_closed_loop.log"
echo "[SUCCES] boucle fermee SUMO -> orchestrateur -> Ryu -> OpenFlow"
