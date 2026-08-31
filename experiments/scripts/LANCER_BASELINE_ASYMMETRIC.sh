#!/bin/bash

# LANCER_BASELINE_ASYMMETRIC.sh
# Test baseline (feux fixes 31s/31s) avec trafic ASYMETRIQUE
# Les feux fixes ne s'adaptent PAS a la demande variable -> performance degradee

set -e

echo "============================================================"
echo "  Test BASELINE avec trafic ASYMETRIQUE (feux fixes)"
echo "  NS fort (0-600s) puis EW fort (600-1200s)"
echo "  Les feux restent a 31s/31s -> sous-optimal"
echo "============================================================"

export SUMO_DIR="/home/jmazeph/experiments/sumo_one_junction"
export RESULTS_DIR="/home/jmazeph/experiments/results"

# Nettoyage
echo ""
echo "Nettoyage..."
pkill -9 sumo 2>/dev/null || true
sleep 2
mkdir -p "$RESULTS_DIR"

if [ ! -f "$SUMO_DIR/one_junction_asymmetric.sumocfg" ]; then
    echo "ERREUR: $SUMO_DIR/one_junction_asymmetric.sumocfg introuvable"
    exit 1
fi

echo "Lancement SUMO baseline asymetrique..."
cd "$SUMO_DIR"

sumo -c one_junction_asymmetric.sumocfg \
    --end 3600 \
    --seed 42 \
    --time-to-teleport -1 \
    --tripinfo-output "$RESULTS_DIR/tripinfo_baseline_asym.xml" \
    --statistic-output "$RESULTS_DIR/stats_baseline_asym.xml" \
    2>&1 | tee "$RESULTS_DIR/sumo_baseline_asym.log"

# Resultats
echo ""
echo "============================================================"
echo "                    RESULTAT BASELINE"
echo "============================================================"

if [ -f "$RESULTS_DIR/tripinfo_baseline_asym.xml" ]; then
    TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_baseline_asym.xml" 2>/dev/null || echo "0")
    echo "Fichier: $RESULTS_DIR/tripinfo_baseline_asym.xml"
    echo "Vehicules termines: $TRIPS"
else
    echo "ERREUR: Fichier non genere"
fi

# Analyser
cd /home/jmazeph/experiments
if [ -f "tools/analyze_sumo.py" ]; then
    python3 tools/analyze_sumo.py \
        --tripinfo "$RESULTS_DIR/tripinfo_baseline_asym.xml" \
        --out "$RESULTS_DIR/sumo_baseline_asym.json"
    echo "JSON: $RESULTS_DIR/sumo_baseline_asym.json"
fi

echo ""
echo "Baseline asymetrique termine."
echo ""
