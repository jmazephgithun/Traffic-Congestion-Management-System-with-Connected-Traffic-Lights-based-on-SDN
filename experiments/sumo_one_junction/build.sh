#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Build the .net.xml from nodes/edges/connections
netconvert   --node-files one_junction.nod.xml   --edge-files one_junction.edg.xml   --connection-files one_junction.con.xml   --tls.guess=false   --output-file one_junction.net.xml

echo "Built one_junction.net.xml"
