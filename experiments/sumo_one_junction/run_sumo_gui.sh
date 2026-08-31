#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Launch SUMO-GUI on TraCI port 8813
sumo-gui -c one_junction.sumocfg --remote-port 8813
