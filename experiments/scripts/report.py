#!/usr/bin/env python3
"""Rapport consolide du niveau 1 : chaque valeur mesuree par le banc Docker est
placee a cote de la valeur publiee dans le memoire (chapitre 3), pour que le
lecteur voie d'un coup d'oeil ce qui est reproduit et ce qui differe.

Les fichiers absents sont signales comme « non execute » : le rapport ne
complete jamais une mesure manquante.
"""
import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path("results_docker")

# Valeurs publiees dans le memoire (chapitre 3, tableaux 3.4 et 3.5, section 4.5).
MEMOIRE = {
    "a3_baseline_completed": 974,
    "a3_adaptive_completed": 1300,
    "a3_baseline_duration": 169.1,
    "a3_adaptive_duration": 169.0,
    "a3_baseline_timeloss": 154.0,
    "a3_adaptive_timeloss": 153.8,
    "a4_blocked_mean": 25.11,
    "a4_blocked_ci": "[24,97 ; 25,25]",
    "webster_mean": 76.5026,
    "webster_ci": "[76,4123 ; 76,5928]",
    "b1_jitter": 110.31, "b1_loss": 69.6, "b1_bw": 0.056,
    "b2_jitter": 0.06, "b2_loss": 0.0, "b2_bw": 0.200,
}


def charger(nom):
    chemin = ROOT / nom
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None


def fr(x, n=2):
    if x is None:
        return "n/d"
    if isinstance(x, int):
        return f"{x:,}".replace(",", " ")
    return f"{x:.{n}f}".replace(".", ",")


def ci(agg, n=2):
    return f"[{fr(agg['ci95_low'], n)} ; {fr(agg['ci95_high'], n)}]"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results_docker/rapport_memoire.md")
    a = p.parse_args()
    L = ["# Rapport consolidé du banc Docker, niveau 1 (reproduction du mémoire)", "",
         f"Généré le {date.today().isoformat()} à partir des fichiers de `results_docker/`.", ""]

    # ------------------------------------------------------------ Phase A
    L += ["## Phase A : mobilité et commande des feux", ""]
    ev = charger("evaluation.json")
    if ev:
        b, ad = ev["baseline"][0], ev["adaptive"][0]
        L += ["### Tableau 3.4, graine 42", "",
              "| Indicateur | Mémoire, feux fixes | Docker, feux fixes | Mémoire, adaptatif | Docker, adaptatif |",
              "|---|---:|---:|---:|---:|",
              f"| Véhicules écoulés sur 1 300 | {MEMOIRE['a3_baseline_completed']} | {b['completed']} | "
              f"{MEMOIRE['a3_adaptive_completed']} | {ad['completed']} |",
              f"| Véhicules bloqués | {1300 - MEMOIRE['a3_baseline_completed']} | {b['blocked']} | 0 | {ad['blocked']} |",
              f"| Durée moyenne de trajet (s) | {fr(MEMOIRE['a3_baseline_duration'], 1)} | {fr(b['duration_mean_s'], 1)} | "
              f"{fr(MEMOIRE['a3_adaptive_duration'], 1)} | {fr(ad['duration_mean_s'], 1)} |",
              f"| Temps perdu moyen (s) | {fr(MEMOIRE['a3_baseline_timeloss'], 1)} | {fr(b['timeloss_mean_s'], 1)} | "
              f"{fr(MEMOIRE['a3_adaptive_timeloss'], 1)} | {fr(ad['timeloss_mean_s'], 1)} |", ""]
    else:
        L += ["Tableau 3.4 : non exécuté (`make test-a3`).", ""]

    ev30 = charger("evaluation-30.json")
    w30 = charger("webster-30.json")
    L += ["### Trente graines appariées et plan Webster", "",
          "| Mesure | Mémoire | Docker |", "|---|---:|---:|"]
    if ev30:
        g = ev30["aggregate"]["paired_completion_gain_points"]
        bc = ev30["aggregate"]["baseline_completion_pct"]
        L += [f"| Véhicules bloqués en feux fixes, moyenne (%) | {fr(MEMOIRE['a4_blocked_mean'])} | {fr(g['mean'])} |",
              f"| IC 95 % des véhicules bloqués | {MEMOIRE['a4_blocked_ci']} | {ci(g)} |",
              f"| Complétion en feux fixes (%) | 74,89 | {fr(bc['mean'])} |",
              f"| Complétion en adaptatif (%) | 100 | {fr(ev30['aggregate']['adaptive_completion_pct']['mean'])} |"]
    else:
        L += ["| Trente graines | publiées | non exécuté (`make evaluate-30`) |"]
    if w30:
        wc = w30["aggregate"]["baseline_completion_pct"]
        L += [f"| Complétion du plan Webster (%) | {fr(MEMOIRE['webster_mean'], 4)} | {fr(wc['mean'], 4)} |",
              f"| IC 95 % du plan Webster | {MEMOIRE['webster_ci']} | {ci(wc, 4)} |"]
    else:
        L += ["| Plan Webster | publié | non exécuté (`make test-a1w`) |"]
    L.append("")

    # ------------------------------------------------------------ Phase B
    L += ["## Phase B : réseau saturé sans et avec QoS SDN (tableau 3.5)", "",
          "Protocole : lien de 5 Mbit/s vers edge, 2 × 8 Mbit/s de trafic de fond, flux de contrôle "
          "UDP/9999 à 200 kbit/s pendant 120 s. Jitter et pertes mesurés côté récepteur.", ""]
    n0 = (charger("ctrl_noqos.json") or {}).get("summary")
    n1 = (charger("ctrl_qos.json") or {}).get("summary")
    if n0 and n1:
        L += ["| Mesure | Mémoire, sans QoS | Docker, sans QoS | Mémoire, avec QoS | Docker, avec QoS |",
              "|---|---:|---:|---:|---:|",
              f"| Jitter moyen (ms) | {fr(MEMOIRE['b1_jitter'])} | {fr(n0['jitter_ms_mean'])} | "
              f"{fr(MEMOIRE['b2_jitter'])} | {fr(n1['jitter_ms_mean'])} |",
              f"| Pertes moyennes (%) | {fr(MEMOIRE['b1_loss'], 1)} | {fr(n0['loss_pct_mean'], 1)} | "
              f"{fr(MEMOIRE['b2_loss'], 1)} | {fr(n1['loss_pct_mean'], 1)} |",
              f"| Débit utile reçu (Mbit/s) | {fr(MEMOIRE['b1_bw'], 3)} | {fr(n0['bw_mbps_mean'], 3)} | "
              f"{fr(MEMOIRE['b2_bw'], 3)} | {fr(n1['bw_mbps_mean'], 3)} |",
              f"| Intervalles mesurés | 119 | {n0['samples']} | 121 | {n1['samples']} |", "",
              "Les valeurs du mémoire proviennent de Mininet-WiFi sur machine Linux ; le banc Docker remplace "
              "les stations Wi-Fi par des espaces de noms réseau. Les ordres de grandeur, et surtout le sens "
              "de l’effet de la QoS, sont ce qui doit être comparé.", ""]
    else:
        L += ["Non exécuté (`make test-b1` puis `make test-b2`).", ""]

    # ------------------------------------------------------------ Boucle fermee
    L += ["## Boucle fermée orchestrateur, Ryu et OpenFlow", ""]
    bf = charger("boucle-fermee-30.json")
    log_orch = ROOT / "orchestrator_closed_loop.log"
    log_ryu = ROOT / "ryu.log"
    if log_orch.exists() and log_ryu.exists():
        switches = log_orch.read_text(errors="replace").count("Switch ->")
        regles = log_ryu.read_text(errors="replace").count("Installed priority rule")
        L += [f"- Exécution intégrée (graine 42) : {switches} changements de phase, "
              f"{regles} installation(s) de la règle prioritaire par Ryu."]
    else:
        L += ["- Exécution intégrée : non exécutée (`make test-c`)."]
    if bf:
        L += [f"- Décision d’hystérésis sur {bf['n_graines']} graines : activation dans "
              f"{bf['n_graines'] - bf['runs_sans_activation']} exécutions sur {bf['n_graines']}, "
              f"priorité active {fr(bf['duty_cycle_pct']['mean'])} % du temps en moyenne "
              f"(min {fr(bf['duty_cycle_pct']['min'])} %, max {fr(bf['duty_cycle_pct']['max'])} %), "
              f"première activation à {fr(bf['premiere_activation_s']['mean'], 1)} s en moyenne."]
    else:
        L += ["- Décision sur trente graines : non exécutée (`make test-c30`)."]
    L.append("")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
