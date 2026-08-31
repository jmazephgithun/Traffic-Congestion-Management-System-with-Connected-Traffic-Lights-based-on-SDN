#!/usr/bin/env bash
set -euo pipefail

OUT=/experiments/results_docker
mkdir -p "$OUT"

fail() { echo "[ECHEC] $*" >&2; exit 1; }
check() { echo "[OK] $*"; }

curl -fsS http://127.0.0.1:8080/health | jq -e '.status == "ok" and .priority_enabled == false' >/dev/null
check "API Ryu disponible"

for ns in car1 car2 car3; do
  ip netns exec "$ns" ping -c 2 -W 2 10.0.0.254 >/dev/null || fail "$ns ne joint pas edge"
done
check "connectivite des quatre namespaces"

curl -fsS -H 'Content-Type: application/json' -d '{"busy":9,"ns_q":5,"ew_q":4}' http://127.0.0.1:8080/metrics \
  | jq -e '.priority == true' >/dev/null
sleep 1
ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep -q 'tp_dst=9999.*set_queue:1' || fail "regle QoS aller absente"
check "activation REST et installation des regles OpenFlow QoS"

ip netns exec edge stdbuf -oL -eL iperf -s -u -p 9999 -i 1 -1 >"$OUT/ctrl_server_qos.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
sleep 1
ip netns exec car1 iperf -c 10.0.0.254 -u -p 9999 -b 1M -t 5 -i 1 >"$OUT/ctrl_client_qos.log" 2>&1 || true
kill "$server_pid" 2>/dev/null || true
wait "$server_pid" 2>/dev/null || true
trap - EXIT
python tools/analyze_iperf.py --log "$OUT/ctrl_client_qos.log" --out "$OUT/ctrl_qos.json" --csv "$OUT/ctrl_qos.csv"
jq -e '.summary.samples > 0 and .summary.bw_mbps_mean > 0' "$OUT/ctrl_qos.json" >/dev/null \
  || { cat "$OUT/ctrl_client_qos.log"; fail "journal iperf inexploitable"; }
ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep 'tp_dst=9999' | grep -Eq 'n_packets=[1-9][0-9]*' \
  || fail "aucun paquet de controle ne traverse la regle prioritaire"
check "trafic UDP mesure et compte par la regle prioritaire"

curl -fsS -H 'Content-Type: application/json' -d '{"busy":2}' http://127.0.0.1:8080/metrics \
  | jq -e '.priority == false' >/dev/null
sleep 1
if ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep -q 'set_queue:1'; then
  fail "la desactivation n'a pas retire les regles QoS"
fi
check "hysteresis et desactivation QoS"

python -m unittest discover -s tests -v
echo "[SUCCES] banc reseau, controleur et tests logiciels valides"
