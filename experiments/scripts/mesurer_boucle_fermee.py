#!/usr/bin/env python3
"""Mesure la boucle fermee orchestrateur -> decision de QoS, sans Ryu ni OVS.

Ce script ne remplace ni ne modifie tls_orchestrator_CORRECTED.py ni
ryu_qos_rest.py : il fait tourner l'orchestrateur REEL, sans le moindre
changement, contre le REEL scenario SUMO, avec --post-url pointe sur un
serveur REST minimal qui reproduit fidelement, ligne pour ligne, la seule
partie de ryu_qos_rest.py testable sans reseau emule : la decision
d'hysteresis de QosRestController.metrics() (ENABLE_THRESHOLD=8.0,
DISABLE_THRESHOLD=3.0). Ce que ce script NE mesure PAS : l'installation
reelle de la regle OpenFlow, ni son effet sur le jitter ou la perte du
flux de controle, qui restent mesures manuellement en Phase B (force_qos_on.sh).
"""
import json, socket, statistics, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path("/home/curtis_dogbo/Projects/Memoire/memoire_3/experiments/experiments")
SUMO_DIR = ROOT / "sumo_one_junction"
SUMO_BIN = Path("/home/curtis_dogbo/Projects/Memoire/.venv/bin/sumo")
PY = Path("/home/curtis_dogbo/Projects/Memoire/.venv/bin/python")
ORCH = ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py"
CFG = SUMO_DIR / "one_junction_asymmetric.sumocfg"
OUT_DIR = ROOT / "results" / "boucle_fermee"

# Reproduction exacte de QosRestSwitch.ENABLE_THRESHOLD / DISABLE_THRESHOLD et de
# la logique d'hysteresis de QosRestController.metrics(), lignes 231-236 de
# pyfilesTrue/ryu_qos_rest.py.
ENABLE_THRESHOLD = 8.0
DISABLE_THRESHOLD = 3.0

SEEDS = [42] + list(range(1, 30))


class Etat:
    def __init__(self):
        self.priority_enabled = False
        self.evenements = []  # (index_requete, busy, ns_q, ew_q, priority)
        self.compte = 0

    def recevoir(self, ns_q, ew_q, busy):
        self.compte += 1
        avant = self.priority_enabled
        # --- reproduction exacte de QosRestController.metrics() ---
        if not self.priority_enabled and busy >= ENABLE_THRESHOLD:
            self.priority_enabled = True
        elif self.priority_enabled and busy <= DISABLE_THRESHOLD:
            self.priority_enabled = False
        # -----------------------------------------------------------
        if self.priority_enabled != avant:
            self.evenements.append((self.compte, busy, ns_q, ew_q, self.priority_enabled))
        return self.priority_enabled


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def lancer_serveur(etat):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            longueur = int(self.headers.get("Content-Length", 0))
            corps = self.rfile.read(longueur)
            try:
                data = json.loads(corps.decode("utf-8"))
            except Exception:
                data = {}
            ns_q = int(data.get("ns_q", 0) or 0)
            ew_q = int(data.get("ew_q", 0) or 0)
            busy = float(data.get("busy", ns_q + ew_q))
            priority = etat.recevoir(ns_q, ew_q, busy)
            reponse = json.dumps({"status": "ok", "busy": busy, "priority": priority}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(reponse)

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

    port = free_port()
    serveur = HTTPServer(("127.0.0.1", port), Handler)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    return serveur, port


def executer_une_graine(seed):
    etat = Etat()
    serveur, port_rest = lancer_serveur(etat)
    try:
        port_sumo = free_port()
        trip = OUT_DIR / f"tripinfo_{seed}.xml"
        sumo_proc = subprocess.Popen(
            [str(SUMO_BIN), "-c", str(CFG), "--remote-port", str(port_sumo),
             "--seed", str(seed), "--time-to-teleport", "-1",
             "--tripinfo-output", str(trip)],
            cwd=SUMO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)
        subprocess.run(
            [str(PY), str(ORCH), "--sumo-port", str(port_sumo), "--tls-id", "J1",
             "--ns-phase-idx", "0", "--ew-phase-idx", "2",
             "--min-green", "10", "--max-green", "45", "--hysteresis", "0.15",
             "--post-url", f"http://127.0.0.1:{port_rest}/metrics"],
            cwd=ROOT, capture_output=True, text=True, timeout=180,
        )
        sumo_proc.wait(timeout=30)
        trip.unlink(missing_ok=True)
    finally:
        serveur.shutdown()

    activations = [e for e in etat.evenements if e[4] is True]
    desactivations = [e for e in etat.evenements if e[4] is False]
    duree_active = 0
    debut_actif = None
    for idx, busy, ns_q, ew_q, priority in etat.evenements:
        if priority:
            debut_actif = idx
        elif debut_actif is not None:
            duree_active += idx - debut_actif
            debut_actif = None
    if debut_actif is not None:
        duree_active += etat.compte - debut_actif

    return {
        "seed": seed,
        "requetes_recues": etat.compte,
        "activations": len(activations),
        "desactivations": len(desactivations),
        "sim_seconds_priorite_active": duree_active,
        "duty_cycle_pct": round(100 * duree_active / etat.compte, 2) if etat.compte else None,
        "premiere_activation_s": activations[0][0] if activations else None,
        "derniere_desactivation_s": desactivations[-1][0] if desactivations else None,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    resultats = []
    for i, seed in enumerate(SEEDS, 1):
        print(f"[{i}/{len(SEEDS)}] graine={seed}", flush=True)
        r = executer_une_graine(seed)
        resultats.append(r)
        print(f"   requetes={r['requetes_recues']} activations={r['activations']} "
              f"duty_cycle={r['duty_cycle_pct']}%", flush=True)

    duty = [r["duty_cycle_pct"] for r in resultats]
    activ = [r["activations"] for r in resultats]
    premiere = [r["premiere_activation_s"] for r in resultats if r["premiere_activation_s"]]

    resume = {
        "n_graines": len(SEEDS),
        "seeds": SEEDS,
        "runs": resultats,
        "duty_cycle_pct": {
            "mean": round(statistics.mean(duty), 2),
            "std": round(statistics.stdev(duty), 2),
            "min": min(duty), "max": max(duty),
        },
        "activations_par_run": {
            "mean": round(statistics.mean(activ), 2),
            "min": min(activ), "max": max(activ),
        },
        "premiere_activation_s": {
            "mean": round(statistics.mean(premiere), 1),
            "min": min(premiere), "max": max(premiere),
        } if premiere else None,
        "runs_sans_activation": sum(1 for r in resultats if r["activations"] == 0),
    }
    out = ROOT / "results" / "boucle_fermee_30_graines.json"
    out.write_text(json.dumps(resume, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nEcrit :", out)
    print(json.dumps({k: v for k, v in resume.items() if k != "runs"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
