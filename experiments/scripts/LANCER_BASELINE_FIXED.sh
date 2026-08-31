#!/bin/bash

# LANCER_BASELINE.sh - Version corrigée
# Usage: bash LANCER_BASELINE.sh

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     Lancement Test BASELINE (Feux Fixes)                  ║"
echo "╚════════════════════════════════════════════════════════════╝"

# CORRECTION: Chemins explicites
export SUMO_DIR="/home/jmazeph/experiments/sumo_one_junction"
export RESULTS_DIR="/home/jmazeph/experiments/results"

# Nettoyage
echo ""
echo "🧹 Nettoyage..."
pkill -9 sumo 2>/dev/null || true
sleep 2

mkdir -p "$RESULTS_DIR"
echo "✅ Prêt"

# Vérifier
if [ ! -d "$SUMO_DIR" ]; then
    echo "❌ ERREUR: $SUMO_DIR n'existe pas"
    exit 1
fi

# Lancer SUMO
echo ""
echo "🟢 Lancement SUMO (5-10 min)..."
cd "$SUMO_DIR"

sumo -c one_junction.sumocfg \
    --end 3600 \
    --seed 42 \
    --time-to-teleport -1 \
    --tripinfo-output "$RESULTS_DIR/tripinfo_baseline.xml" \
    --statistic-output "$RESULTS_DIR/stats_baseline.xml" \
    2>&1 | tee "$RESULTS_DIR/sumo_baseline.log"

# Résultats
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    RÉSULTAT                                ║"
echo "╚════════════════════════════════════════════════════════════╝"

if [ -f "$RESULTS_DIR/tripinfo_baseline.xml" ]; then
    TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_baseline.xml" 2>/dev/null || echo "0")
    echo ""
    echo "✅ Fichier: $RESULTS_DIR/tripinfo_baseline.xml"
    echo "   Véhicules: $TRIPS"

    if [ "$TRIPS" -eq 928 ]; then
        echo "   ✅ Tous terminés!"
    else
        echo "   ⚠️  Attendu: 928"
    fi

    END_TIME=$(grep "Simulation ended" "$RESULTS_DIR/sumo_baseline.log" 2>/dev/null | grep -oP "time: \K[0-9.]+")
    if [ -n "$END_TIME" ]; then
        echo "   Durée sim: ${END_TIME}s"
    fi
else
    echo ""
    echo "❌ Fichier non généré"
fi

echo ""
echo "📁 Log: $RESULTS_DIR/sumo_baseline.log"
echo ""
