#!/bin/bash

# LANCER_ADAPTIVE_CORRECTED.sh - Avec logique de switching corrigée

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     Test ADAPTIVE (Version CORRIGÉE)                       ║"
echo "║     Devrait ALTERNER entre phase 0 (NS) et 2 (EW)         ║"
echo "╚════════════════════════════════════════════════════════════╝"

export SUMO_DIR="/home/jmazeph/experiments/sumo_one_junction"
export MAIN_DIR="/home/jmazeph/experiments"
export RESULTS_DIR="/home/jmazeph/experiments/results"

# Nettoyage
echo ""
echo "🧹 Nettoyage..."
pkill -9 sumo 2>/dev/null || true
sleep 3
mkdir -p "$RESULTS_DIR"
echo "✅ Prêt"

if [ ! -f "$MAIN_DIR/pyfilesTrue/tls_orchestrator_CORRECTED.py" ]; then
    echo "❌ tls_orchestrator_CORRECTED.py non trouvé"
    exit 1
fi

# Lancer SUMO
echo ""
echo "🟢 Lancement SUMO..."
cd "$SUMO_DIR"

sumo -c one_junction.sumocfg \
    --remote-port 8813 \
    --end 3600 \
    --seed 42 \
    --time-to-teleport -1 \
    --tripinfo-output "$RESULTS_DIR/tripinfo_adaptive.xml" \
    --statistic-output "$RESULTS_DIR/stats_adaptive.xml" \
    > "$RESULTS_DIR/sumo_adaptive.log" 2>&1 &

SUMO_PID=$!
echo "   SUMO PID: $SUMO_PID"

# Attendre port
echo ""
echo "⏳ Attente du port 8813..."
for i in {1..30}; do
    if netstat -an 2>/dev/null | grep -q "8813.*LISTEN"; then
        echo "   ✅ Port 8813 écoute (tentative $i)"
        break
    fi
    sleep 1
done

if ! ps -p $SUMO_PID > /dev/null 2>&1; then
    echo "❌ SUMO mort!"
    tail -30 "$RESULTS_DIR/sumo_adaptive.log"
    exit 1
fi

echo "✅ SUMO tourne"

# Lancer orchestrateur CORRIGÉ
echo ""
echo "🔵 Lancement orchestrateur CORRIGÉ (logique de switching fixée)..."
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
    2>&1 | tee "$RESULTS_DIR/orchestrator.log"

wait $SUMO_PID 2>/dev/null || true

# Résultats
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    RÉSULTAT                                ║"
echo "╚════════════════════════════════════════════════════════════╝"

if [ -f "$RESULTS_DIR/tripinfo_adaptive.xml" ]; then
    TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_adaptive.xml" 2>/dev/null || echo "0")
    echo ""
    echo "✅ Fichier: $RESULTS_DIR/tripinfo_adaptive.xml"
    echo "   Véhicules: $TRIPS"

    if [ "$TRIPS" -eq 928 ]; then
        echo "   ✅✅✅ SUCCÈS COMPLET (928 véhicules)!"
    elif [ "$TRIPS" -gt 800 ]; then
        echo "   ✅ Très bon ($TRIPS véhicules)!"
    elif [ "$TRIPS" -gt 0 ]; then
        echo "   ⚠️  Partiel ($TRIPS véhicules, attendu: 928)"
    else
        echo "   ❌ Aucun véhicule"
    fi
else
    echo ""
    echo "❌ Fichier non généré"
fi

echo ""
echo "📁 Logs:"
echo "   - $RESULTS_DIR/sumo_adaptive.log"
echo "   - $RESULTS_DIR/orchestrator.log"

# Compter switchs et vérifier alternance
if [ -f "$RESULTS_DIR/orchestrator.log" ]; then
    SWITCHES_NS=$(grep -c "Switch -> NS_GREEN" "$RESULTS_DIR/orchestrator.log" 2>/dev/null || echo "0")
    SWITCHES_EW=$(grep -c "Switch -> EW_GREEN" "$RESULTS_DIR/orchestrator.log" 2>/dev/null || echo "0")
    TOTAL_SWITCHES=$((SWITCHES_NS + SWITCHES_EW))

    echo ""
    echo "📊 Changements de phase:"
    echo "   NS_GREEN: $SWITCHES_NS"
    echo "   EW_GREEN: $SWITCHES_EW"
    echo "   TOTAL:    $TOTAL_SWITCHES"

    if [ "$SWITCHES_EW" -gt 0 ]; then
        echo "   ✅✅✅ ALTERNANCE FONCTIONNE!"
    else
        echo "   ❌ Pas d'alternance (toujours sur NS)"
    fi

    if [ "$TOTAL_SWITCHES" -gt 20 ]; then
        echo "   ✅ Beaucoup de changements (adaptatif actif)"
    elif [ "$TOTAL_SWITCHES" -gt 5 ]; then
        echo "   ✅ Nombre raisonnable de changements"
    else
        echo "   ⚠️  Peu de changements"
    fi
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "    Cherchez 'Switch -> EW_GREEN' dans les logs!"
echo "    Si présent → BUG CORRIGÉ ✅"
echo "═══════════════════════════════════════════════════════════"
echo ""
