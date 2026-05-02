#!/bin/bash

# COMPARER_RESULTATS.sh - Version CORRIGÉE

set -e

# CORRECTION: Chemin explicite
export RESULTS_DIR="/home/jmazeph/experiments/results"
export MAIN_DIR="/home/jmazeph/experiments"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        COMPARAISON BASELINE vs ADAPTIVE                    ║"
echo "╚════════════════════════════════════════════════════════════╝"

# Vérifier fichiers
echo ""
echo "🔍 Vérification des fichiers..."

if [ ! -f "$RESULTS_DIR/tripinfo_baseline.xml" ]; then
    echo "❌ Fichier baseline manquant!"
    echo "   $RESULTS_DIR/tripinfo_baseline.xml"
    echo "   Lancez d'abord: bash scripts/LANCER_BASELINE_FIXED.sh"
    exit 1
fi

if [ ! -f "$RESULTS_DIR/tripinfo_adaptive.xml" ]; then
    echo "❌ Fichier adaptive manquant!"
    echo "   $RESULTS_DIR/tripinfo_adaptive.xml"
    echo "   Lancez d'abord: bash scripts/LANCER_ADAPTIVE_CORRECTED.sh"
    exit 1
fi

echo "✅ Fichiers trouvés"
echo "   $RESULTS_DIR/tripinfo_baseline.xml"
echo "   $RESULTS_DIR/tripinfo_adaptive.xml"

# Compter véhicules
BASELINE_TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_baseline.xml" 2>/dev/null || echo "0")
ADAPTIVE_TRIPS=$(grep -c '<tripinfo ' "$RESULTS_DIR/tripinfo_adaptive.xml" 2>/dev/null || echo "0")

echo ""
echo "📊 Véhicules complétés:"
echo "   Baseline: $BASELINE_TRIPS"
echo "   Adaptive: $ADAPTIVE_TRIPS"

# Analyser avec script Python
echo ""
echo "📈 Analyse détaillée..."
cd "$MAIN_DIR"

# Vérifier si analyze_sumo.py existe
ANALYZE_SCRIPT=""
if [ -f "thesis_reporting_kit_min/scripts/analyze_sumo.py" ]; then
    ANALYZE_SCRIPT="thesis_reporting_kit_min/scripts/analyze_sumo.py"
elif [ -f "tools/analyze_sumo.py" ]; then
    ANALYZE_SCRIPT="tools/analyze_sumo.py"
elif [ -f "analyze_sumo.py" ]; then
    ANALYZE_SCRIPT="analyze_sumo.py"
fi

if [ -n "$ANALYZE_SCRIPT" ]; then
    echo "   Utilisation de: $ANALYZE_SCRIPT"

    python3 "$ANALYZE_SCRIPT" \
        --tripinfo "$RESULTS_DIR/tripinfo_baseline.xml" \
        --out "$RESULTS_DIR/sumo_baseline.json" 2>/dev/null || echo "⚠️  Erreur baseline"

    python3 "$ANALYZE_SCRIPT" \
        --tripinfo "$RESULTS_DIR/tripinfo_adaptive.xml" \
        --out "$RESULTS_DIR/sumo_adaptive.json" 2>/dev/null || echo "⚠️  Erreur adaptive"

    echo "✅ Fichiers JSON générés"

    # Comparaison
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║                      COMPARAISON                           ║"
    echo "╚════════════════════════════════════════════════════════════╝"

    python3 << EOF
import json
import sys

try:
    with open("$RESULTS_DIR/sumo_baseline.json") as f:
        baseline = json.load(f)["summary"]

    with open("$RESULTS_DIR/sumo_adaptive.json") as f:
        adaptive = json.load(f)["summary"]

    print()
    print("=" * 60)
    print("BASELINE (Feux Fixes)".center(60))
    print("=" * 60)
    print(f"  Véhicules:    {baseline.get('total_vehicles', 'N/A')}")
    print(f"  Durée moy:    {baseline.get('duration_s_mean', 0):.1f} s")
    print(f"  Temps perdu:  {baseline.get('timeloss_s_mean', 0):.1f} s")
    print(f"  Vitesse moy:  {baseline.get('mean_speed_mps', 0):.2f} m/s")
    print(f"  Throughput:   {baseline.get('throughput_vph', 0):.1f} veh/h")

    print()
    print("=" * 60)
    print("ADAPTIVE (Orchestrateur Corrigé)".center(60))
    print("=" * 60)
    print(f"  Véhicules:    {adaptive.get('total_vehicles', 'N/A')}")
    print(f"  Durée moy:    {adaptive.get('duration_s_mean', 0):.1f} s")
    print(f"  Temps perdu:  {adaptive.get('timeloss_s_mean', 0):.1f} s")
    print(f"  Vitesse moy:  {adaptive.get('mean_speed_mps', 0):.2f} m/s")
    print(f"  Throughput:   {adaptive.get('throughput_vph', 0):.1f} veh/h")

    print()
    print("=" * 60)
    print("DIFFÉRENCES".center(60))
    print("=" * 60)

    def pct_change(old, new):
        if old == 0 or old is None or new is None:
            return "N/A"
        change = ((new - old) / old) * 100
        return f"{change:+.1f}%"

    baseline_tp = baseline.get('throughput_vph', 0)
    adaptive_tp = adaptive.get('throughput_vph', 0)
    ratio = (adaptive_tp / baseline_tp * 100) if baseline_tp > 0 else 0

    print(f"  Durée:        {pct_change(baseline.get('duration_s_mean'), adaptive.get('duration_s_mean'))}")
    print(f"  Temps perdu:  {pct_change(baseline.get('timeloss_s_mean'), adaptive.get('timeloss_s_mean'))}")
    print(f"  Vitesse:      {pct_change(baseline.get('mean_speed_mps'), adaptive.get('mean_speed_mps'))}")
    print(f"  Throughput:   {pct_change(baseline_tp, adaptive_tp)}")

    print()
    print("=" * 60)
    print(f"Ratio Adaptive/Baseline: {ratio:.1f}%".center(60))
    print("=" * 60)
    print()

    if ratio >= 95:
        print("✅✅✅ EXCELLENT! Adaptive >= 95% baseline")
        print("       Le bug est COMPLÈTEMENT FIXÉ!")
        sys.exit(0)
    elif ratio >= 90:
        print("✅✅ TRÈS BON! Adaptive >= 90% baseline")
        print("     Le bug est fixé!")
        sys.exit(0)
    elif ratio >= 80:
        print("✅ BON! Adaptive >= 80% baseline")
        print("   Peut-être améliorer les paramètres (min_green, max_green)")
        sys.exit(0)
    elif ratio >= 50:
        print("⚠️  MOYEN. Adaptive >= 50% baseline")
        print("    Les paramètres peuvent être optimisés")
        sys.exit(0)
    else:
        print("❌ ÉCHEC. Adaptive << baseline")
        print("   Problème de configuration")
        sys.exit(1)

except FileNotFoundError as e:
    print(f"❌ Fichier non trouvé: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

else
    echo "⚠️  Script analyze_sumo.py non trouvé"
    echo "   Chemins testés:"
    echo "   - thesis_reporting_kit_min/scripts/analyze_sumo.py"
    echo "   - tools/analyze_sumo.py"
    echo "   - analyze_sumo.py"
    echo ""
    echo "   Comparaison MANUELLE:"
    echo "   Baseline: $BASELINE_TRIPS véhicules"
    echo "   Adaptive: $ADAPTIVE_TRIPS véhicules"

    if [ "$BASELINE_TRIPS" -eq "$ADAPTIVE_TRIPS" ]; then
        echo "   ✅ Même nombre de véhicules!"
    else
        echo "   ⚠️  Nombres différents"
    fi
fi

echo ""
echo "📁 Fichiers résultats:"
echo "   $RESULTS_DIR/tripinfo_baseline.xml"
echo "   $RESULTS_DIR/tripinfo_adaptive.xml"
echo "   $RESULTS_DIR/sumo_baseline.json"
echo "   $RESULTS_DIR/sumo_adaptive.json"
echo ""
