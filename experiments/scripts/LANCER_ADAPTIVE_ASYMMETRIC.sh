#!/bin/bash

# LANCER_ADAPTIVE_ASYMMETRIC.sh
# Test adaptatif avec trafic ASYMETRIQUE
# L'orchestrateur detecte que NS est plus charge et donne plus de vert NS
# Puis quand EW devient charge, il bascule -> performance amelioree

set -e

echo "============================================================"
echo "  Test ADAPTIVE avec trafic ASYMETRIQUE"
echo "  L'orchestrateur adapte les feux a la demande variable"
echo "============================================================"

export SUMO_DIR="/home/jmazeph/experiments/sumo_one_junction"
export MAIN_DIR="/home/jmazeph/experiments"
export RESULTS_DIR="/home/jmazeph/experiments/results"

# Nettoyage
echo ""
echo "Nettoyage..."
pkill -9 sumo 2>/dev/null || true
sleep 3
mkdir -p "$RESULTS_DIR"

if [ ! -f "$MAIN_DIR/pyfilesTrue/tls_orchestrator_CORRECTED.py" ]; then
    echo "ERREUR: tls_orchestrator_CORRECTED.py introuvable"
    exit 1
fi

# Lancer SUMO en mode remote (attend la connexion TraCI)
echo ""
echo "Lancement SUMO avec remote-port 8813..."
cd "$SUMO_DIR"

sumo -c one_junction_asymmetric.sumocfg \
    --remote-port 8813 \
    --end 3600 \
    --seed 42 \
    --time-to-teleport -1 \
    --tripinfo-output "$RESULTS_DIR/tripinfo_adaptive_asym.xml" \
    --statistic-output "$RESULTS_DIR/stats_adaptive_asym.xml" \
    > "$RESULTS_DIR/sumo_adaptive_asym.log" 2>&1 &

SUMO_PID=$!
echo "SUMO PID: $SUMO_PID"

# Attendre le port
echo ""
echo "Attente du port 8813..."
for i in {1..30}; do
    if netstat -an 2>/dev/null | grep -q "8813.*LISTEN"; then
        echo "Port 8813 ecoute (tentative $i)"
        break
    fi
    if ss -lntu 2>/dev/null | grep -q ":8813"; then
        echo "Port 8813 ecoute (tentative $i)"
        break
    fi
    sleep 1
done

if ! ps -p $SUMO_PID > /dev/null 2>&1; then
    echo "ERREUR: SUMO mort"
    tail -30 "$RESULTS_DIR/sumo_adaptive_asym.log"
    exit 1
fi

# Lancer orchestrateur AVEC --post-url pour le lien avec Ryu
echo ""
echo "Lancement orchestrateur adaptatif..."
echo "  (avec --post-url pour envoyer les metriques a Ryu si actif)"
cd "$MAIN_DIR"

if [ "$(id -u)" -eq 0 ]; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="sudo -E python3"
fi

$PYTHON_CMD pyfilesTrue/tls_orchestrator_CORRECTED.py \
    --sumo-port 8813 \
    --tls-id J1 \
    --ns-phase-idx 0 \
    --ew-phase-idx 2 \
    --min-green 10 \
    --max-green 45 \
    --hysteresis 0.15 \
    --post-url http://localhost:8080/metrics \
    2>&1 | tee "$RESULTS_DIR/orchestrator_asym.log"

wait $SUMO_PID 2>/dev/null || true

# Resultats
echo ""
echo "============================================================"
echo "                    RESULTAT ADAPTIVE"
echo "============================================================"

if [ -f "$RESULTS_DIR/tripinfo_adaptive_asym.xml" ]; then
    TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_adaptive_asym.xml" 2>/dev/null || echo "0")
    echo "Fichier: $RESULTS_DIR/tripinfo_adaptive_asym.xml"
    echo "Vehicules termines: $TRIPS"
else
    echo "ERREUR: Fichier non genere"
fi

# Compter les switchs
if [ -f "$RESULTS_DIR/orchestrator_asym.log" ]; then
    SWITCHES_NS=$(grep -c "Switch -> NS_GREEN" "$RESULTS_DIR/orchestrator_asym.log" 2>/dev/null || echo "0")
    SWITCHES_EW=$(grep -c "Switch -> EW_GREEN" "$RESULTS_DIR/orchestrator_asym.log" 2>/dev/null || echo "0")
    echo ""
    echo "Changements de phase:"
    echo "  NS_GREEN: $SWITCHES_NS"
    echo "  EW_GREEN: $SWITCHES_EW"
    echo "  TOTAL:    $((SWITCHES_NS + SWITCHES_EW))"
fi

# Analyser
cd /home/jmazeph/experiments
if [ -f "tools/analyze_sumo.py" ]; then
    python3 tools/analyze_sumo.py \
        --tripinfo "$RESULTS_DIR/tripinfo_adaptive_asym.xml" \
        --out "$RESULTS_DIR/sumo_adaptive_asym.json"
    echo "JSON: $RESULTS_DIR/sumo_adaptive_asym.json"
fi

echo ""
echo "Adaptive asymetrique termine."
echo ""
