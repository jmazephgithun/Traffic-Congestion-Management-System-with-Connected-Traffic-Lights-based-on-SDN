#!/usr/bin/env python3
"""Regenere la Figure 3.6 (representation du carrefour J1) a partir du reseau SUMO reel.

Le memoire remis a l'instructeur ne contenait aucune image a l'emplacement prevu pour
cette figure (legende presente, paragraphes reserves vides, aucune donnee binaire) : le
defaut est verifiable dans relecture/originaux/MEMOIRE_ACHI_FINAL_INSTRUCTION.docx et n'a
pas ete introduit par les corrections de ce depot.

Plutot que d'inserer une image d'origine non etablie, ce script reconstruit un schema du
carrefour directement a partir du fichier reseau qui a servi aux experiences,
sumo_one_junction/one_junction.net.xml : quatre branches, la jonction a feux J1 au centre,
et le sens de chaque voie tel qu'il est reellement modelise.

Dependances : matplotlib, sumolib (pip install matplotlib sumolib).

Usage :
  python3 scripts/generer_figure_3_6.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sumolib

RACINE = Path(__file__).resolve().parents[3]
RESEAU = RACINE / "experiments" / "experiments" / "sumo_one_junction" / "one_junction.net.xml"
SORTIE = RACINE / "redaction" / "figures" / "Figure_3_6_Carrefour_J1.png"

COULEUR_ENTREE = "#1F3864"
COULEUR_SORTIE = "#8FA3C4"
DECALAGE = 3.2


def decale(p1, p2, delta):
    """Decale un segment perpendiculairement a sa direction, pour separer les deux sens."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    longueur = (dx**2 + dy**2) ** 0.5
    nx, ny = -dy / longueur, dx / longueur
    return (x1 + nx * delta, y1 + ny * delta), (x2 + nx * delta, y2 + ny * delta)


def main() -> None:
    net = sumolib.net.readNet(str(RESEAU))
    cx, cy = net.getNode("J1").getCoord()

    fig, ax = plt.subplots(figsize=(6.6, 6.6), dpi=200)

    for edge in net.getEdges():
        shape = edge.getShape()
        p1, p2 = shape[0], shape[-1]
        vers_j1 = edge.getToNode().getID() == "J1"
        couleur = COULEUR_ENTREE if vers_j1 else COULEUR_SORTIE
        delta = DECALAGE if vers_j1 else -DECALAGE
        (ax1, ay1), (ax2, ay2) = decale(p1, p2, delta)
        ax.plot([ax1, ax2], [ay1, ay2], color=couleur, linewidth=5,
                solid_capstyle="round", zorder=2)
        if vers_j1:
            fx, fy = ax1 + (ax2 - ax1) * 0.62, ay1 + (ay2 - ay1) * 0.62
        else:
            fx, fy = ax1 + (ax2 - ax1) * 0.38, ay1 + (ay2 - ay1) * 0.38
        dx, dy = (ax2 - ax1) * 0.001, (ay2 - ay1) * 0.001
        ax.annotate("", xy=(fx + dx * 300, fy + dy * 300), xytext=(fx, fy),
                    arrowprops=dict(arrowstyle="-|>", color=couleur, lw=0, mutation_scale=18),
                    zorder=3)

    ax.add_patch(plt.Circle((cx, cy), 6.5, facecolor="#2e2e2e", edgecolor="black", zorder=4))
    for i, c in enumerate(("#c0392b", "#e1b12c", "#27ae60")):
        ax.add_patch(plt.Circle((cx, cy + 9 - i * 4), 1.3, facecolor=c, edgecolor="none", zorder=5))
    ax.text(cx + 11, cy - 11, "J1", ha="left", va="top", fontsize=13, fontweight="bold",
            color="#1F3864", zorder=6,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))

    noms = {"N": "Nord (N)", "S": "Sud (S)", "E": "Est (E)", "W": "Ouest (W)"}
    for node_id, texte in noms.items():
        x, y = net.getNode(node_id).getCoord()
        dx, dy = (x - cx) * 0.12, (y - cy) * 0.12
        ax.text(x + dx, y + dy, texte, ha="center", va="center", fontsize=11,
                fontweight="bold", color="#333333", zorder=6,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))

    ax.plot([], [], color=COULEUR_ENTREE, linewidth=5, label="Voie entrante vers J1")
    ax.plot([], [], color=COULEUR_SORTIE, linewidth=5, label="Voie sortante depuis J1")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.06), ncol=1, frameon=False, fontsize=9)

    ax.set_aspect("equal")
    ax.axis("off")
    marge = 30
    ax.set_xlim(cx - 100 - marge, cx + 100 + marge)
    ax.set_ylim(cy - 100 - marge, cy + 100 + marge)
    plt.tight_layout()
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(SORTIE, facecolor="white", bbox_inches="tight")
    print(f"Figure ecrite : {SORTIE}")


if __name__ == "__main__":
    main()
