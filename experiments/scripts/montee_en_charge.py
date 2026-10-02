#!/usr/bin/env python3
"""Montee en charge : comment evolue l'apport de la commande adaptative quand
le nombre de vehicules augmente ?

La demande de chaque scenario est multipliee par un facteur (option --scale de
SUMO, qui conserve le profil asymetrique et l'alternance des pointes), du trafic
leger jusqu'a plusieurs fois la capacite du carrefour. Pour chaque palier et
chaque politique, les simulations vont jusqu'a la sortie du dernier vehicule
(base egale, comme make evaluation-equitable), et l'on mesure le retard total
moyen par vehicule.

Sorties : montee-en-charge.json, montee-en-charge.md et une courbe SVG par
scenario (retard total en fonction du nombre de vehicules).

Le Webster de chaque scenario est calcule pour la demande nominale (facteur 1) et
n'est pas recalcule a chaque palier : c'est le cas d'un plan fixe regle une fois
pour toutes, ce que sont les feux fixes sur le terrain.
"""
import argparse
import json
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluation_equitable import SCENARIOS, LIBELLE, executer, ic95, parse_seeds  # noqa: E402

PALIERS = {
    "j1_corrige": [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4],
    "alternance": [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4],
    "solibra": [0.1, 0.25, 0.5, 0.75, 1, 1.5, 2],
}
POLITIQUES = ["fixe", "webster", "adaptatif_memoire", "adaptatif_v2"]
COULEUR = {"fixe": "#c0392b", "webster": "#8e6c1f", "adaptatif_memoire": "#7f8c8d", "adaptatif_v2": "#1f4e9c"}


def fr(x, n=0):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",")


def courbe_svg(titre, series, chemin):
    """series : {politique: [(vehicules, retard_moyen), ...]} -> fichier SVG."""
    W, H, g, d, h, b = 760, 420, 70, 20, 40, 60
    xs = [x for pts in series.values() for x, _ in pts]
    ys = [y for pts in series.values() for _, y in pts]
    xmax, ymax = max(xs) * 1.02, max(ys) * 1.08 or 1
    X = lambda x: g + (W - g - d) * x / xmax
    Y = lambda y: H - b - (H - h - b) * y / ymax
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'font-family="Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{W/2}" y="22" text-anchor="middle" font-size="14" font-weight="bold">{titre}</text>']
    for k in range(6):
        y = ymax * k / 5
        o.append(f'<line x1="{g}" x2="{W-d}" y1="{Y(y):.1f}" y2="{Y(y):.1f}" stroke="#e3e6ea"/>')
        o.append(f'<text x="{g-8}" y="{Y(y)+4:.1f}" text-anchor="end" fill="#555">{fr(y)}</text>')
    for k in range(6):
        x = xmax * k / 5
        o.append(f'<text x="{X(x):.1f}" y="{H-b+18}" text-anchor="middle" fill="#555">{fr(x)}</text>')
    o.append(f'<text x="{(g+W-d)/2}" y="{H-b+40}" text-anchor="middle">Nombre de véhicules injectés</text>')
    o.append(f'<text transform="translate(18,{(h+H-b)/2}) rotate(-90)" text-anchor="middle">'
             'Retard total moyen par véhicule (s)</text>')
    for k, (pol, pts) in enumerate(series.items()):
        pts = sorted(pts)
        chemin_pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
        o.append(f'<polyline points="{chemin_pts}" fill="none" stroke="{COULEUR[pol]}" stroke-width="2.5"/>')
        for x, y in pts:
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.5" fill="{COULEUR[pol]}"/>')
        lx, ly = g + 12, h + 14 + 18 * k
        o.append(f'<line x1="{lx}" x2="{lx+22}" y1="{ly}" y2="{ly}" stroke="{COULEUR[pol]}" stroke-width="3"/>')
        o.append(f'<text x="{lx+28}" y="{ly+4}">{LIBELLE[pol]}</text>')
    o.append("</svg>")
    Path(chemin).write_text("\n".join(o), encoding="utf-8")


def courbe_ecarts(series, chemin):
    """series : {titre_scenario: [(vehicules, ecart_pct), ...]} -> SVG, ecart v2 / feux fixes."""
    W, H, g, d, h, b = 760, 420, 70, 20, 40, 60
    couleurs = ["#1f4e9c", "#1f9d55", "#c0392b"]
    xs = [x for pts in series.values() for x, _ in pts]
    ys = [y for pts in series.values() for _, y in pts]
    xmax = max(xs) * 1.02
    ymin, ymax = min(min(ys), -10) * 1.1, max(max(ys), 10) * 1.1
    X = lambda x: g + (W - g - d) * x / xmax
    Y = lambda y: h + (H - h - b) * (ymax - y) / (ymax - ymin)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'font-family="Arial, sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{W/2}" y="22" text-anchor="middle" font-size="14" font-weight="bold">'
         'Écart de retard de l’orchestrateur v2 par rapport aux feux fixes</text>']
    for k in range(7):
        y = ymin + (ymax - ymin) * k / 6
        o.append(f'<line x1="{g}" x2="{W-d}" y1="{Y(y):.1f}" y2="{Y(y):.1f}" stroke="#e3e6ea"/>')
        o.append(f'<text x="{g-8}" y="{Y(y)+4:.1f}" text-anchor="end" fill="#555">{fr(y)} %</text>')
    o.append(f'<line x1="{g}" x2="{W-d}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="#333" stroke-width="1.5"/>')
    o.append(f'<text x="{W-d-4}" y="{Y(0)-6:.1f}" text-anchor="end" fill="#333">aucun écart</text>')
    for k in range(6):
        x = xmax * k / 5
        o.append(f'<text x="{X(x):.1f}" y="{H-b+18}" text-anchor="middle" fill="#555">{fr(x)}</text>')
    o.append(f'<text x="{(g+W-d)/2}" y="{H-b+40}" text-anchor="middle">Nombre de véhicules injectés</text>')
    o.append(f'<text transform="translate(18,{(h+H-b)/2}) rotate(-90)" text-anchor="middle">'
             'Retard total, v2 par rapport aux feux fixes (%)</text>')
    for k, (titre, pts) in enumerate(series.items()):
        c = couleurs[k % len(couleurs)]
        pts = sorted(pts)
        o.append(f'<polyline points="{" ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)}" fill="none" '
                 f'stroke="{c}" stroke-width="2.5"/>')
        for x, y in pts:
            o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.5" fill="{c}"/>')
        lx, ly = W - d - 330, H - b - 70 + 18 * k
        o.append(f'<line x1="{lx}" x2="{lx+22}" y1="{ly}" y2="{ly}" stroke="{c}" stroke-width="3"/>')
        o.append(f'<text x="{lx+28}" y="{ly+4}">{titre}</text>')
    o.append("</svg>")
    Path(chemin).write_text("\n".join(o), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,1-4")
    ap.add_argument("--scenarios", default="j1_corrige,alternance,solibra")
    ap.add_argument("--facteurs", default=None,
                    help="paliers communs a tous les scenarios, ex. 0.5,1,2,4,8 (sinon paliers par defaut)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--output", default="results_docker/montee-en-charge.json")
    ap.add_argument("--rapport-seul", action="store_true",
                    help="reconstruit tableaux et courbes a partir du JSON existant, sans simuler")
    a = ap.parse_args()
    graines = parse_seeds(a.seeds)
    scen = a.scenarios.split(",")
    paliers = {s: ([float(f) for f in a.facteurs.split(",")] if a.facteurs else PALIERS[s]) for s in scen}
    taches = [(s, p, g, f) for s in scen for f in paliers[s] for p in POLITIQUES for g in graines
              if not (p == "webster" and SCENARIOS[s]["webster"] is None)]
    res = []
    if a.rapport_seul:
        ancien = json.loads(Path(a.output).read_text(encoding="utf-8"))
        res, graines = ancien["executions"], ancien["graines"]
        paliers = {s: [float(f) for f in ancien["paliers"][s]] for s in scen}
        taches = []
    print(f"{len(taches)} simulations, {a.workers} en parallele", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futurs = [ex.submit(executer, *t) for t in taches]
        for k, fu in enumerate(as_completed(futurs), 1):
            r = fu.result()
            res.append(r)
            print(f"[{k}/{len(taches)}] {r['scenario']} x{r['echelle']} {r['politique']} graine={r['graine']} "
                  f"vehicules={r['vehicules']} retard={r['retard_total_s']:.0f}s", flush=True)

    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    synthese, ecarts = {}, {}
    L = ["# Montée en charge", "", "![Écarts](montee-en-charge-ecart.svg)", "",
         f"{len(graines)} graine(s) par palier. Chaque simulation va jusqu’à la sortie du dernier véhicule. "
         "Retard total = attente avant d’entrer dans le réseau + temps perdu dans le réseau. "
         "Écart = variation du retard de l’orchestrateur v2 par rapport aux feux fixes, apparié par graine.", ""]
    for s in scen:
        synthese[s] = {}
        series = {}
        L += [f"## {SCENARIOS[s]['titre']}", "", f"![Courbe](montee-en-charge-{s}.svg)", "",
              "| Facteur | Véhicules | Feux fixes (s) | Webster (s) | Adaptatif mémoire (s) | Adaptatif v2 (s) | Écart v2 / fixes |",
              "|---:|---:|---:|---:|---:|---:|---:|"]
        for f in paliers[s]:
            bloc = {}
            for p in POLITIQUES:
                rs = [r for r in res if r["scenario"] == s and r["echelle"] == f and r["politique"] == p]
                if rs:
                    bloc[p] = {"vehicules": round(statistics.mean(r["vehicules"] for r in rs)),
                               "retard_total_s": ic95([r["retard_total_s"] for r in rs]),
                               "vidage_s": ic95([r["vidage_s"] for r in rs])}
                    series.setdefault(p, []).append((bloc[p]["vehicules"], bloc[p]["retard_total_s"]["moyenne"]))
            fixe = {r["graine"]: r["retard_total_s"] for r in res if r["scenario"] == s and r["echelle"] == f and r["politique"] == "fixe"}
            v2 = [r for r in res if r["scenario"] == s and r["echelle"] == f and r["politique"] == "adaptatif_v2"]
            ecart = ic95([100 * (r["retard_total_s"] - fixe[r["graine"]]) / fixe[r["graine"]] for r in v2 if fixe.get(r["graine"])])
            bloc["ecart_v2_vs_fixe_pct"] = ecart
            ecarts.setdefault(SCENARIOS[s]["court"], []).append((bloc["fixe"]["vehicules"], ecart["moyenne"]))
            synthese[s][str(f)] = bloc
            cel = lambda p: fr(bloc[p]["retard_total_s"]["moyenne"]) if p in bloc else "n/d"
            L.append(f"| ×{fr(f, 2).rstrip('0').rstrip(',')} | {fr(bloc['fixe']['vehicules'])} | {cel('fixe')} | {cel('webster')} | "
                     f"{cel('adaptatif_memoire')} | {cel('adaptatif_v2')} | {fr(ecart['moyenne'], 1)} % |")
        L.append("")
        courbe_svg(SCENARIOS[s]["titre"], series, out.parent / f"montee-en-charge-{s}.svg")
    courbe_ecarts(ecarts, out.parent / "montee-en-charge-ecart.svg")
    out.write_text(json.dumps({"graines": graines, "paliers": paliers, "synthese": synthese, "executions": res},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    out.with_suffix(".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
