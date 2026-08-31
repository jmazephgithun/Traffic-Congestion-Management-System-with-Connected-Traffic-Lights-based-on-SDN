#!/bin/bash
set -e
cd /experiments
mkdir -p /experiments/results_docker

if [ "${SKIP_NETWORK:-0}" = "1" ]; then
    exec "$@"
fi

echo "[entrypoint] lancement de Ryu (ryu_qos_rest.py, fichier non modifie)"
ryu-manager pyfilesTrue/ryu_qos_rest.py > /experiments/results_docker/ryu.log 2>&1 &
RYU_PID=$!

echo "[entrypoint] attente de l'API REST Ryu sur :8080/health"
for i in $(seq 1 30); do
    curl -s http://127.0.0.1:8080/health >/dev/null 2>&1 && break
    sleep 1
done
curl -s http://127.0.0.1:8080/health && echo || { echo "[entrypoint] Ryu n'a pas demarre" >&2; cat /experiments/results_docker/ryu.log; exit 1; }

bash /experiments/docker/bringup_topologie.sh

echo "[entrypoint] attente de la connexion OpenFlow du pont ap1 a Ryu"
for i in $(seq 1 30); do
    grep -q "Switch MAIN" /experiments/results_docker/ryu.log 2>/dev/null && break
    sleep 1
done
grep "Switch MAIN\|FeaturesReply" /experiments/results_docker/ryu.log || echo "[entrypoint] ATTENTION : pas de confirmation OpenFlow dans les logs Ryu"

if [ "$#" -eq 0 ]; then
    set -- bash
fi
exec "$@"
