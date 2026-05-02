#!/usr/bin/env python3
import time, traci

PORT=8812  # a free port just for baseline
traci.connect(port=PORT)
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()
    # time.sleep(0.0)  # optional
traci.close()
print("Baseline finished to completion.")

