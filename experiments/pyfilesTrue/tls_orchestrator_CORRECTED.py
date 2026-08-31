#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive TLS Orchestrator - VERSION CORRIGÉE

BUG TROUVÉ: La logique de décision ne changeait jamais target_phase correctement!
"""

import argparse, time, sys
import traceback

try:
    import requests
except Exception:
    requests = None

import traci

def log(msg):
    print(f"[orchestrator] {msg}", flush=True)

# ---------- helpers ----------

def connect_traci(port: int, host: str = "127.0.0.1"):
    """Connect and do a couple of warm-up steps so TL API is ready."""
    tr = traci.connect(port=port, host=host)
    log(f"Connected to SUMO on port {port}")

    # Warm-up a few steps (safe even if no vehicles yet)
    for _ in range(3):
        try:
            tr.simulationStep()
        except Exception:
            break
        time.sleep(0.02)

    return tr

def wait_for_tls(tr, tls_id, timeout_s=5.0):
    """Step until tls_id appears (or timeout)."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if tls_id in tr.trafficlight.getIDList():
                return True
            tr.simulationStep()
            time.sleep(0.02)
        except traci.exceptions.FatalTraCIError:
            raise
        except Exception:
            time.sleep(0.02)
    return False

def sum_edges(tr, edges, fn='veh'):
    """Return queue/veh counts across edges."""
    total = 0
    for e in edges:
        try:
            if fn == 'halt':
                total += tr.edge.getLastStepHaltingNumber(e)
            else:
                total += tr.edge.getLastStepVehicleNumber(e)
        except Exception:
            pass
    return total

def post_metrics(url, ns_q, ew_q):
    if not url or not requests:
        return None, None

    busy = float(ns_q + ew_q)
    payload = {'ns_q': int(ns_q), 'ew_q': int(ew_q), 'busy': busy}

    try:
        r = requests.post(url, json=payload, timeout=1.0)
        return r.status_code, r.text[:200]
    except Exception:
        return None, None

def find_phase_indices(tr, tls_id, ns_edges, ew_edges):
    """Find indices of phases where NS or EW lanes are green."""
    lanes = tr.trafficlight.getControlledLanes(tls_id)

    lane_edges = []
    for ln in lanes:
        try:
            lane_edges.append(tr.lane.getEdgeID(ln))
        except Exception:
            lane_edges.append(ln.split('_')[0])

    ns_idx_set = {i for i, ed in enumerate(lane_edges) if ed in ns_edges}
    ew_idx_set = {i for i, ed in enumerate(lane_edges) if ed in ew_edges}

    logics = tr.trafficlight.getAllProgramLogics(tls_id)
    phases = logics[0].phases if logics else []

    ns_idx = ew_idx = 0

    def phase_has_green(phase_state, idx_set):
        return any(phase_state[i] in ('g', 'G') for i in idx_set if i < len(phase_state))

    for i, ph in enumerate(phases):
        st = ph.state
        if phase_has_green(st, ns_idx_set) and ns_idx == 0:
            ns_idx = i
        if phase_has_green(st, ew_idx_set) and ew_idx == 0:
            ew_idx = i

    if ns_idx == ew_idx:
        ns_idx, ew_idx = (0, 1) if len(phases) > 1 else (0, 0)

    log(f"Phase indices: NS_GREEN={ns_idx}, EW_GREEN={ew_idx}")
    return ns_idx, ew_idx

# ---------- main control ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sumo-port', type=int, required=True)
    ap.add_argument('--tls-id', required=True)
    ap.add_argument('--ns', nargs='*', default=None, help='NS edge IDs (optional)')
    ap.add_argument('--ew', nargs='*', default=None, help='EW edge IDs (optional)')
    ap.add_argument('--ns-phase-idx', type=int, default=None, help='Force NS green phase index')
    ap.add_argument('--ew-phase-idx', type=int, default=None, help='Force EW green phase index')
    ap.add_argument('--min-green', type=float, default=10.0)
    ap.add_argument('--max-green', type=float, default=45.0)
    ap.add_argument('--hysteresis', type=float, default=0.15)
    ap.add_argument('--post-url', default=None)
    ap.add_argument('--realtime', action='store_true',
                    help='Synchronise SUMO avec le temps reel (1s sim = 1s reel). '
                         'Indispensable pour les tests reseau simultanes avec iperf.')
    ap.add_argument('--realtime-factor', type=float, default=1.0,
                    help='Facteur de temps reel (1.0 = temps reel, 2.0 = 2x plus vite). '
                         'Utilisé seulement avec --realtime.')
    args = ap.parse_args()

    # connect
    try:
        tr = connect_traci(args.sumo_port)
    except Exception as e:
        log(f"Could not connect to SUMO: {e}")
        sys.exit(1)

    try:
        if not wait_for_tls(tr, args.tls_id, timeout_s=8.0):
            log(f"TLS '{args.tls_id}' not found (timeout).")
            tr.close(False)
            sys.exit(1)

        # edges
        if args.ns and args.ew:
            ns_edges = args.ns
            ew_edges = args.ew
            log(f"Using explicit edges. NS={ns_edges} EW={ew_edges}")
        else:
            all_edges = [e for e in tr.edge.getIDList() if '2' in e or 'J1' in e]
            ns_edges = [e for e in all_edges if e.startswith('N') or e.startswith('S')]
            ew_edges = [e for e in all_edges if e.startswith('E') or e.startswith('W')]
            if not ns_edges or not ew_edges:
                ns_edges = ['N2J1', 'S2J1']
                ew_edges = ['E2J1', 'W2J1']
            log(f"Auto-detected edges. NS={ns_edges}  EW={ew_edges}")

        tr.simulationStep()

        if args.ns_phase_idx is not None and args.ew_phase_idx is not None:
            ns_green_idx = args.ns_phase_idx
            ew_green_idx = args.ew_phase_idx
            log(f"Using FORCED indices: NS={ns_green_idx}, EW={ew_green_idx}")
        else:
            ns_green_idx, ew_green_idx = find_phase_indices(tr, args.tls_id, ns_edges, ew_edges)

        log(f"Loop (min={args.min_green}s, max={args.max_green}s, hyst={args.hysteresis})")

        # ═══════════════════════════════════════════════════════════
        # LOGIQUE CORRIGÉE - Le bug était ici!
        # ═══════════════════════════════════════════════════════════

        # Forcer la phase initiale à NS
        tr.trafficlight.setPhase(args.tls_id, ns_green_idx)
        current_phase = ns_green_idx
        last_switch_time = tr.simulation.getTime()

        log(f"Starting with NS_GREEN (phase={ns_green_idx})")
        if args.realtime:
            log(f"Mode TEMPS REEL active (facteur={args.realtime_factor}x)")
            log(f"La simulation va durer aussi longtemps qu'en temps reel.")
            log(f"Vous avez le temps de lancer iperf dans Mininet!")

        wall_start = time.time()
        sim_start = tr.simulation.getTime()

        while True:
            tr.simulationStep()
            now = tr.simulation.getTime()

            # Synchronisation temps reel : attendre que le temps reel rattrape
            if args.realtime:
                sim_elapsed = now - sim_start
                wall_target = sim_elapsed / args.realtime_factor
                wall_elapsed = time.time() - wall_start
                sleep_time = wall_target - wall_elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            ns_q = sum_edges(tr, ns_edges, fn='veh')
            ew_q = sum_edges(tr, ew_edges, fn='veh')
            elapsed = now - last_switch_time

            # Décision de changement
            should_switch = False
            new_phase = current_phase

            if current_phase == ns_green_idx:
                # Actuellement NS vert
                # Condition 1: EW a beaucoup plus de véhicules (hystérésis)
                ew_pressure = ew_q > ns_q * (1.0 + args.hysteresis)
                # Condition 2: Temps max atteint
                max_time_reached = elapsed >= args.max_green

                if (ew_pressure or max_time_reached) and elapsed >= args.min_green:
                    should_switch = True
                    new_phase = ew_green_idx

            else:  # current_phase == ew_green_idx
                # Actuellement EW vert
                # Condition 1: NS a beaucoup plus de véhicules (hystérésis)
                ns_pressure = ns_q > ew_q * (1.0 + args.hysteresis)
                # Condition 2: Temps max atteint
                max_time_reached = elapsed >= args.max_green

                if (ns_pressure or max_time_reached) and elapsed >= args.min_green:
                    should_switch = True
                    new_phase = ns_green_idx

            # Appliquer le changement
            if should_switch:
                tr.trafficlight.setPhase(args.tls_id, new_phase)
                current_phase = new_phase
                last_switch_time = now
                name = "NS_GREEN" if new_phase == ns_green_idx else "EW_GREEN"
                log(f"Switch -> {name} (phase={new_phase}) [NS_q={ns_q}, EW_q={ew_q}, elapsed={elapsed:.1f}s]")

            post_metrics(args.post_url, ns_q, ew_q)

            if int(now) % 5 == 0:
                phase_name = "NS" if current_phase == ns_green_idx else "EW"
                log(f"[{now:6.2f}s] queues: NS={ns_q:3}  EW={ew_q:3}  phase={current_phase}({phase_name})  elapsed={elapsed:.1f}s")

            if tr.simulation.getMinExpectedNumber() == 0:
                break

        log("SUMO finished.")
        tr.close(False)

    except traci.exceptions.FatalTraCIError as e:
        log(f"TraCI fatal error: {e}")
        try:
            tr.close(False)
        except Exception:
            pass
        sys.exit(1)

    except KeyboardInterrupt:
        try:
            tr.close(False)
        except Exception:
            pass

    except Exception as e:
        log(f"Unhandled error: {e}\n{traceback.format_exc()}")
        try:
            tr.close(False)
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
