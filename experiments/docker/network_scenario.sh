#!/usr/bin/env bash
# Phase B du memoire : flux de controle des feux (UDP/9999) en concurrence avec
# un trafic de fond qui sature volontairement le lien vers edge.
#
# Protocole identique a celui du chapitre 3 (Tableau 3.5) :
#   - lien ap1 -> edge limite a BW_EDGE (5 Mbit/s) ;
#   - car2 et car3 emettent chacun BG_RATE (8 Mbit/s), soit 16 Mbit/s offerts ;
#   - car1 emet le flux de controle a CTRL_RATE (200 kbit/s) ;
#   - duree DURATION (120 s), mesure par intervalle d'une seconde.
#
# Le jitter et les pertes UDP ne sont calcules par iperf2 que cote recepteur :
# c'est donc le journal du serveur (edge) qui est analyse. stdbuf force une
# ecriture ligne par ligne pour que l'arret du serveur ne perde aucun intervalle.
set -euo pipefail
MODE=${1:?usage: network_scenario.sh noqos|qos}
[ "$MODE" = noqos ] || [ "$MODE" = qos ] || { echo "mode invalide" >&2; exit 2; }

CTRL_RATE=${CTRL_RATE:-200K}
BG_RATE=${BG_RATE:-8M}
DURATION=${DURATION:-120}
OUT=/experiments/results_docker
mkdir -p "$OUT"

if [ "$MODE" = qos ]; then
  # busy=20 depasse le seuil d'activation de Ryu (8) : la regle prioritaire est installee.
  curl -fsS -H 'Content-Type: application/json' -d '{"busy":20}' http://127.0.0.1:8080/metrics \
    | jq -e '.priority == true' >/dev/null
  sleep 1
  ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep -q 'tp_dst=9999.*set_queue:1' \
    || { echo "[ECHEC] regle QoS absente apres activation" >&2; exit 1; }
else
  curl -fsS http://127.0.0.1:8080/health | jq -e '.priority_enabled == false' >/dev/null
fi

echo "[phase B] mode=$MODE controle=$CTRL_RATE fond=2x$BG_RATE duree=${DURATION}s lien=${BW_EDGE:-5}Mbit/s"

# stdbuf : le journal du serveur est ecrit ligne par ligne, aucun intervalle
# n'est perdu quand le serveur est arrete en fin de mesure.
ip netns exec edge stdbuf -oL -eL iperf -s -u -p 9999 -i 1 >"$OUT/ctrl_server_${MODE}.log" 2>&1 & p1=$!
ip netns exec edge iperf -s -u -p 5001 >/dev/null 2>&1 & p2=$!
ip netns exec edge iperf -s -u -p 5002 >/dev/null 2>&1 & p3=$!
trap 'kill $p1 $p2 $p3 2>/dev/null || true' EXIT
sleep 1

# Le trafic de fond demarre avant le flux de controle et s'arrete apres lui,
# pour que toute la mesure se deroule sur un lien sature.
BG_DURATION=$((DURATION + 4))
ip netns exec car2 iperf -c 10.0.0.254 -u -p 5001 -b "$BG_RATE" -t "$BG_DURATION" >/dev/null 2>&1 & c2=$!
ip netns exec car3 iperf -c 10.0.0.254 -u -p 5002 -b "$BG_RATE" -t "$BG_DURATION" >/dev/null 2>&1 & c3=$!
sleep 2
ip netns exec car1 iperf -c 10.0.0.254 -u -p 9999 -b "$CTRL_RATE" -t "$DURATION" -i 1 \
  >"$OUT/ctrl_client_${MODE}.log" 2>&1 || true
wait "$c2" "$c3" || true
sleep 1
kill -INT "$p1" "$p2" "$p3" 2>/dev/null || true
wait "$p1" "$p2" "$p3" 2>/dev/null || true
trap - EXIT

if [ "$MODE" = qos ]; then
  ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep 'tp_dst=9999' >"$OUT/ctrl_flow_qos.txt" || true
  curl -fsS -H 'Content-Type: application/json' -d '{"busy":0}' http://127.0.0.1:8080/metrics >/dev/null || true
fi

python tools/analyze_iperf.py --log "$OUT/ctrl_server_${MODE}.log" --out "$OUT/ctrl_${MODE}.json" --csv "$OUT/ctrl_${MODE}.csv"
jq -e '.summary.samples > 0 and .summary.role_hint == "server"' "$OUT/ctrl_${MODE}.json" >/dev/null \
  || { echo "[ECHEC] journal serveur sans jitter/pertes exploitables" >&2; tail -20 "$OUT/ctrl_server_${MODE}.log" >&2; exit 1; }
jq -r --arg m "$MODE" '.summary | "[phase B] \($m) debit=\(.bw_mbps_mean) Mbit/s jitter=\(.jitter_ms_mean) ms pertes=\(.loss_pct_mean) %"' \
  "$OUT/ctrl_${MODE}.json"
echo "[SUCCES] scenario reseau $MODE -> $OUT/ctrl_${MODE}.json"
