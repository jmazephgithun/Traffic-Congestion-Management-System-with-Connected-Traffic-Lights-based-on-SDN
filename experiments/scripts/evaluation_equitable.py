#!/usr/bin/env python3
"""Evaluation a base egale des politiques de feux.

Le protocole du memoire arrete les feux fixes a 3 600 s mais laisse la simulation
adaptative continuer jusqu'a la sortie du dernier vehicule : les deux variantes ne
sont pas comparees sur la meme duree. Ici, chaque simulation tourne jusqu'a ce que
TOUS les vehicules soient sortis, et l'on compare ce que vivent ces vehicules :

  - retard total moyen : attente avant d'entrer dans le reseau (file d'insertion,
    departDelay) + temps perdu dans le reseau (timeLoss), par vehicule ;
  - attente moyenne dans le reseau (waitingTime) ;
  - duree de vidage : instant de sortie du dernier vehicule ;
  - vehicules sortis a 1 200 s, 1 800 s et 3 600 s (meme horizon pour tous).

Politiques : feux fixes, plan Webster (quand il existe pour le scenario),
orchestrateur du memoire, orchestrateur version 2 (option evoluee).
Scenarios : carrefour J1 du memoire, carrefour reel de Solibra, alternance sous la
capacite. Les executions sont appariees par graine.
"""
import argparse
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMO = ROOT / "sumo_one_junction"
ORCH = {"adaptatif_memoire": ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py",
        "adaptatif_v2": ROOT / "pyfilesTrue" / "tls_orchestrator_v2.py"}
SCENARIOS = {
    "j1": {"titre": "Carrefour J1 du mémoire (saturé, 1 300 véhicules)",
           "fixe": "one_junction_asymmetric.sumocfg", "webster": "one_junction_asymmetric_webster.sumocfg"},
    "solibra": {"titre": "Carrefour réel de Solibra (saturé, 5 852 véhicules)",
                "fixe": "one_junction_asymmetric_solibra.sumocfg", "webster": None},
    "j1_corrige": {"titre": "Carrefour J1, phases corrigées (Nord+Sud / Est+Ouest), demande du mémoire",
                   "fixe": "one_junction_corrige.sumocfg", "webster": "one_junction_corrige_webster.sumocfg"},
    "alternance": {"titre": "Alternance sous la capacité (J1 aux phases corrigées, 1 736 véhicules, Y = 0,72)",
                   "fixe": "one_junction_alternance.sumocfg", "webster": "one_junction_alternance_webster.sumocfg"},
}
POLITIQUES = ["fixe", "webster", "adaptatif_memoire", "adaptatif_v2"]
LIBELLE = {"fixe": "Feux fixes", "webster": "Plan Webster", "adaptatif_memoire": "Adaptatif (mémoire)",
           "adaptatif_v2": "Adaptatif v2"}
HORIZONS = (1200, 1800, 3600)


def parse_seeds(v):
    out = []
    for part in v.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b) + 1) if b else [int(a)])
    return list(dict.fromkeys(out))


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def executer(scenario, politique, graine):
    cfg = SCENARIOS[scenario]["webster" if politique == "webster" else "fixe"]
    with tempfile.TemporaryDirectory() as tmp:
        trip = Path(tmp) / "trip.xml"
        cmd = ["sumo", "-c", str(SUMO / cfg), "--seed", str(graine), "--end", "40000",
               "--time-to-teleport", "-1", "--tripinfo-output", str(trip), "--no-warnings", "true",
               "--no-step-log", "true"]
        if politique in ORCH:
            port = port_libre()
            sumo = subprocess.Popen(cmd + ["--remote-port", str(port)], cwd=SUMO,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            subprocess.run([sys.executable, str(ORCH[politique]), "--sumo-port", str(port), "--tls-id", "J1",
                            "--ns-phase-idx", "0", "--ew-phase-idx", "2", "--min-green", "10",
                            "--max-green", "45", "--hysteresis", "0.15"],
                           cwd=ROOT, capture_output=True, timeout=7200)
            sumo.wait(timeout=120)
        else:
            subprocess.run(cmd, cwd=SUMO, capture_output=True, timeout=7200, check=True)
        v = [(float(e.get("arrival")), float(e.get("departDelay")), float(e.get("timeLoss")),
              float(e.get("waitingTime"))) for _, e in ET.iterparse(trip) if e.tag == "tripinfo"]
    arr = [x[0] for x in v]
    return {"scenario": scenario, "politique": politique, "graine": graine, "vehicules": len(v),
            "retard_total_s": statistics.mean(x[1] + x[2] for x in v),
            "attente_reseau_s": statistics.mean(x[3] for x in v),
            "vidage_s": max(arr),
            **{f"sortis_{h}s": sum(a <= h for a in arr) for h in HORIZONS}}


def ic95(valeurs):
    m = statistics.mean(valeurs)
    d = 0.0 if len(valeurs) < 2 else 1.96 * statistics.stdev(valeurs) / math.sqrt(len(valeurs))
    return {"moyenne": round(m, 2), "ic95": [round(m - d, 2), round(m + d, 2)], "n": len(valeurs)}


def fr(x, n=1):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,1-29")
    ap.add_argument("--scenarios", default="j1,j1_corrige,solibra,alternance")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--output", default="results_docker/evaluation-equitable.json")
    a = ap.parse_args()
    graines = parse_seeds(a.seeds)
    taches = [(s, p, g) for s in a.scenarios.split(",") for p in POLITIQUES for g in graines
              if not (p == "webster" and SCENARIOS[s]["webster"] is None)]
    print(f"{len(taches)} simulations, {a.workers} en parallele", flush=True)
    res = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futurs = [ex.submit(executer, *t) for t in taches]
        for k, f in enumerate(as_completed(futurs), 1):
            r = f.result()
            res.append(r)
            print(f"[{k}/{len(taches)}] {r['scenario']} {r['politique']} graine={r['graine']} "
                  f"retard={r['retard_total_s']:.0f}s vidage={r['vidage_s']:.0f}s", flush=True)

    synthese = {}
    for s in a.scenarios.split(","):
        synthese[s] = {}
        ref = {r["graine"]: r for r in res if r["scenario"] == s and r["politique"] == "fixe"}
        for p in POLITIQUES:
            rs = [r for r in res if r["scenario"] == s and r["politique"] == p]
            if not rs:
                continue
            bloc = {k: ic95([r[k] for r in rs]) for k in
                    ["retard_total_s", "attente_reseau_s", "vidage_s"] + [f"sortis_{h}s" for h in HORIZONS]}
            if p != "fixe":
                ecarts = [100 * (r["retard_total_s"] - ref[r["graine"]]["retard_total_s"]) / ref[r["graine"]]["retard_total_s"]
                          for r in rs if r["graine"] in ref]
                bloc["ecart_retard_vs_fixe_pct"] = ic95(ecarts)
            synthese[s][p] = bloc
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"protocole": {"graines": graines, "base": "tous les vehicules sortis"},
                               "synthese": synthese, "executions": res}, indent=2, ensure_ascii=False),
                   encoding="utf-8")

    L = ["# Évaluation à base égale", "",
         f"{len(graines)} graine(s) appariée(s). Chaque simulation tourne jusqu’à la sortie du dernier véhicule. "
         "Retard total = attente avant d’entrer dans le réseau + temps perdu dans le réseau. "
         "Les intervalles sont des IC à 95 %.", ""]
    for s, blocs in synthese.items():
        L += [f"## {SCENARIOS[s]['titre']}", "",
              "| Politique | Retard total moyen (s) | Écart vs feux fixes | Vidage (s) | Sortis à 1 800 s | Sortis à 3 600 s |",
              "|---|---:|---:|---:|---:|---:|"]
        for p, b in blocs.items():
            e = b.get("ecart_retard_vs_fixe_pct")
            ecart = "référence" if e is None else f"{fr(e['moyenne'])} % [{fr(e['ic95'][0])} ; {fr(e['ic95'][1])}]"
            L.append(f"| {LIBELLE[p]} | {fr(b['retard_total_s']['moyenne'], 0)} | {ecart} | "
                     f"{fr(b['vidage_s']['moyenne'], 0)} | {fr(b['sortis_1800s']['moyenne'], 0)} | "
                     f"{fr(b['sortis_3600s']['moyenne'], 0)} |")
        L.append("")
    out.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
