SUMO One-Junction Starter (TLS id: J1)
=====================================

Files
-----
- one_junction.nod.xml : Nodes (J1 + N/S/E/W)
- one_junction.edg.xml : Edges (N2J1, S2J1, E2J1, W2J1, J1toN, J1toS, J1toE, J1toW)
- one_junction.con.xml : Exactly 4 straight-through controlled links with fixed linkIndex order
- one_junction.add.xml : Explicit 2-phase tlLogic for J1 (NS green, then EW green)
- one_junction.rou.xml : Simple straight flows from all approaches (600 veh/h each)
- one_junction.sumocfg : SUMO configuration (step-length=0.5)
- build.sh             : Build the .net.xml with netconvert
- run_sumo_gui.sh      : Run SUMO GUI with TraCI on port 8813

Build & Run
-----------
chmod +x build.sh run_sumo_gui.sh
./build.sh
./run_sumo_gui.sh

TraCI / Orchestrator
--------------------
Use these IDs in your controller:
- TLS id    : J1
- NS edges  : N2J1 S2J1
- EW edges  : E2J1 W2J1

Example orchestrator call:
python3 tls_orchestrator.py --sumo-port 8813 --tls-id J1 --ns N2J1 S2J1 --ew E2J1 W2J1
