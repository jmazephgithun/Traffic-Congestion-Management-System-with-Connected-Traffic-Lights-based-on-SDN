#!/bin/bash
# Bureau virtuel (Xvfb) + gestionnaire de fenetres (fluxbox) + sumo-gui,
# capture VNC (x11vnc) exposee en HTML5 par noVNC/websockify sur :6080.
#
# Par defaut : carrefour reel de Solibra sur fond OpenStreetMap, feux pilotes
# en direct par l'orchestrateur adaptatif du memoire (MODE=adaptatif).
# MODE=fixe montre le meme trafic sous le programme de feux statique.
set -e
export DISPLAY=:99
Xvfb :99 -screen 0 1280x800x24 &
sleep 1
fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1

CFG="${SUMO_CFG:-sumo_one_junction/one_junction_asymmetric_solibra.sumocfg}"
MODE="${MODE:-adaptatif}"
cd /experiments
GUI_OPTS=(-c "$CFG" --start --quit-on-end false --window-size 1260,760 --window-pos 10,10
          --delay "${SUMO_DELAY:-60}" --time-to-teleport -1)

if [ "$MODE" = adaptatif ]; then
    echo "[gui] sumo-gui pilote par l'orchestrateur adaptatif (TraCI)"
    sumo-gui "${GUI_OPTS[@]}" --remote-port 8813 >/tmp/sumo-gui.log 2>&1 &
    sleep 3
    python pyfilesTrue/tls_orchestrator_CORRECTED.py --sumo-port 8813 --tls-id J1 \
        --ns-phase-idx 0 --ew-phase-idx 2 --min-green 10 --max-green 45 --hysteresis 0.15 \
        >/tmp/orchestrateur.log 2>&1 &
else
    echo "[gui] sumo-gui avec le programme de feux fixe"
    sumo-gui "${GUI_OPTS[@]}" >/tmp/sumo-gui.log 2>&1 &
fi

x11vnc -display :99 -forever -shared -nopw -quiet -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
sleep 1
echo "[gui] ouvrir http://localhost:6080/vnc.html?autoconnect=true&resize=scale"
websockify --web=/usr/share/novnc 6080 localhost:5900
