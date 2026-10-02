#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orchestrateur adaptatif, version 2 (option evoluee du depot).

Le fichier tls_orchestrator_CORRECTED.py, utilise dans le memoire, n'est pas
modifie. Cette version garde la meme interface (memes options, meme publication
des metriques vers Ryu) et corrige trois limites mises en evidence par le banc :

1. Demande cachee : la version du memoire ne compte que les vehicules presents
   sur les troncons d'approche (au plus une vingtaine par voie). En saturation,
   des centaines de vehicules attendent avant meme d'entrer dans le reseau et
   restent invisibles. Ici, la pression d'un axe additionne les vehicules sur
   ses troncons et ceux qui attendent leur insertion sur ces troncons.

2. Vert inutile : un axe au vert qui n'a plus aucun vehicule garde le vert
   jusqu'a ce que l'autre axe le depasse de 15 %. Ici, le vert est rendu des que
   l'axe servi est vide et que l'autre attend (regle classique du « gap-out »
   des feux actionnes), et il n'est jamais rendu a un axe vide.

3. Phase orange : la version du memoire passe directement d'un vert a l'autre.
   Ici, chaque changement passe par la phase orange du programme du carrefour,
   avec sa duree, comme le font les feux fixes : la comparaison est loyale.
"""
import argparse
import sys

try:
    import requests
except Exception:
    requests = None

import traci


def log(msg):
    print(f"[orchestrateur-v2] {msg}", flush=True)


def post_metrics(url, ns_q, ew_q):
    """Meme publication que la version du memoire : busy = vehicules sur les troncons."""
    if not url or not requests:
        return
    try:
        requests.post(url, json={"ns_q": int(ns_q), "ew_q": int(ew_q), "busy": float(ns_q + ew_q)}, timeout=1.0)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sumo-port", type=int, required=True)
    ap.add_argument("--tls-id", required=True)
    ap.add_argument("--ns-phase-idx", type=int, default=0)
    ap.add_argument("--ew-phase-idx", type=int, default=2)
    ap.add_argument("--min-green", type=float, default=10.0)
    ap.add_argument("--max-green", type=float, default=45.0)
    ap.add_argument("--hysteresis", type=float, default=0.15)
    ap.add_argument("--post-url", default=None)
    a = ap.parse_args()

    tr = traci.connect(port=a.sumo_port)
    tls = a.tls_id
    tr.simulationStep()

    # Troncons d'approche de chaque axe, deduits des voies commandees par le feu
    # et des phases vertes du programme actif.
    voies = tr.trafficlight.getControlledLanes(tls)
    programme = tr.trafficlight.getProgram(tls)
    logique = next(l for l in tr.trafficlight.getAllProgramLogics(tls) if l.programID == programme)
    phases = logique.phases

    def troncons(idx):
        etat = phases[idx].state
        return {tr.lane.getEdgeID(v) for i, v in enumerate(voies) if i < len(etat) and etat[i] in "gG"}

    axes = {"NS": a.ns_phase_idx, "EW": a.ew_phase_idx}
    entree = {nom: troncons(idx) for nom, idx in axes.items()}
    orange = {nom: (idx + 1) % len(phases) for nom, idx in axes.items()}
    duree_orange = {nom: phases[orange[nom]].duration for nom in axes}
    log(f"troncons NS={sorted(entree['NS'])} EW={sorted(entree['EW'])} orange={duree_orange}")

    axe_du_vehicule = {}                             # cache : l'itineraire d'un vehicule ne change pas

    def mesure():
        sur_troncons = {nom: sum(tr.edge.getLastStepVehicleNumber(e) for e in ed) for nom, ed in entree.items()}
        en_attente = {"NS": 0, "EW": 0}
        for vid in tr.simulation.getPendingVehicles():
            if vid not in axe_du_vehicule:
                try:
                    premier = tr.vehicle.getRoute(vid)[0]
                except Exception:
                    premier = None
                axe_du_vehicule[vid] = next((nom for nom, ed in entree.items() if premier in ed), None)
            nom = axe_du_vehicule[vid]
            if nom:
                en_attente[nom] += 1
        return sur_troncons, en_attente

    vert = "NS"
    tr.trafficlight.setPhase(tls, axes[vert])
    tr.trafficlight.setPhaseDuration(tls, 1e6)      # l'orchestrateur decide seul de la fin du vert
    debut_vert = tr.simulation.getTime()
    fin_orange, cible = None, None
    changements = 0

    while tr.simulation.getMinExpectedNumber() > 0:
        tr.simulationStep()
        t = tr.simulation.getTime()
        sur, att = mesure()
        pression = {nom: sur[nom] + att[nom] for nom in axes}
        post_metrics(a.post_url, sur["NS"], sur["EW"])

        if fin_orange is not None:                  # orange en cours
            if t >= fin_orange:
                vert, fin_orange = cible, None
                tr.trafficlight.setPhase(tls, axes[vert])
                tr.trafficlight.setPhaseDuration(tls, 1e6)
                debut_vert = t
            continue

        autre = "EW" if vert == "NS" else "NS"
        ecoule = t - debut_vert
        if ecoule < a.min_green or pression[autre] == 0:
            continue
        servi_vide = sur[vert] == 0 and att[vert] == 0
        plus_charge = pression[autre] > pression[vert] * (1.0 + a.hysteresis)
        if servi_vide or plus_charge or ecoule >= a.max_green:
            tr.trafficlight.setPhase(tls, orange[vert])
            fin_orange, cible = t + duree_orange[vert], autre
            changements += 1
            if changements % 20 == 1:
                log(f"t={t:.0f}s Switch -> {autre} (pression NS={pression['NS']} EW={pression['EW']}, vert={ecoule:.0f}s)")

    log(f"Simulation terminee, {changements} changements de phase.")
    tr.close(False)


if __name__ == "__main__":
    sys.exit(main())
