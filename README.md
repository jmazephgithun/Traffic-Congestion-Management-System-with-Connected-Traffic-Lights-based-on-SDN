# Traffic Congestion Management with Connected Traffic Lights based on SDN

[![CI](https://github.com/jmazephgithun/Traffic-Congestion-Management-System-with-Connected-Traffic-Lights-based-on-SDN/actions/workflows/ci.yml/badge.svg)](https://github.com/jmazephgithun/Traffic-Congestion-Management-System-with-Connected-Traffic-Lights-based-on-SDN/actions/workflows/ci.yml)

Ce dépôt présente une solution de gestion adaptative de la congestion combinant
SUMO/TraCI, un orchestrateur de feux, Ryu/OpenFlow et Open vSwitch avec QoS HTB.

## Expérimentation reproductible

Le banc conteneurisé se trouve dans [`experiments/`](experiments/README.md). Il est
organisé en deux niveaux :

| Niveau | Commande | Objet |
|---|---|---|
| 1. Reproduction du mémoire | `make memoire` | Rejoue les phases A et B, la boucle fermée et le plan Webster, puis compare chaque valeur mesurée à la valeur publiée |
| 2. Option évoluée | `make evolue` | Contrôleurs par secteur (Abidjan Nord et Sud) avec secours, carrefour réel de Solibra, rejeu comparatif, interface graphique SUMO |

```bash
cd experiments
make build      # une seule fois
make demo       # démonstration visuelle commentée : experiments/results_docker/demo.html
make gui        # SUMO en direct dans le navigateur : http://localhost:6080
make memoire    # niveau 1
make evolue     # niveau 2
```

![Démonstration sur la carte réelle de Solibra](experiments/docs/captures/demo_carte_solibra.png)

Seul Docker est nécessaire ; la section 1 du [mode d’emploi](experiments/README.md)
explique son installation sous Windows (WSL 2), Ubuntu et macOS.

- [`experiments/README.md`](experiments/README.md) : mode d’emploi complet ;
- [`experiments/ARCHITECTURE.md`](experiments/ARCHITECTURE.md) : composants et flux de décision ;
- [`experiments/VALIDATION.md`](experiments/VALIDATION.md) : valeurs réellement mesurées, comparées au mémoire.

Les résultats sont produits localement dans `experiments/results_docker/` et ne
sont pas versionnés.

## Implémentation historique

Le dossier `Achi Master Project/` conserve les scripts, documents et résultats de
l’implémentation initiale. Pour toute nouvelle reproduction, utiliser en priorité
le banc conteneurisé sous `experiments/`.

## Organisation

```text
.
├── experiments/           # version reproductible et maintenue
│   ├── docker/             # image, démarrage et scénarios réseau
│   ├── pyfilesTrue/        # orchestrateur et contrôleur Ryu
│   ├── scripts/            # évaluation et rapport
│   ├── sumo_one_junction/  # réseau et demandes SUMO
│   ├── tests/              # tests unitaires
│   └── tools/              # analyse des mesures
└── Achi Master Project/    # archive de l’implémentation initiale
```
