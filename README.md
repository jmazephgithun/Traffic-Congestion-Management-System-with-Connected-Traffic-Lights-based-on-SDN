# Traffic Congestion Management with Connected Traffic Lights based on SDN

[![CI](https://github.com/jmazephgithun/Traffic-Congestion-Management-System-with-Connected-Traffic-Lights-based-on-SDN/actions/workflows/ci.yml/badge.svg)](https://github.com/jmazephgithun/Traffic-Congestion-Management-System-with-Connected-Traffic-Lights-based-on-SDN/actions/workflows/ci.yml)

Ce dépôt présente une solution de gestion adaptative de la congestion combinant
SUMO/TraCI, un orchestrateur de feux, Ryu/OpenFlow et Open vSwitch avec QoS HTB.

## Expérimentation reproductible

La version Docker complète se trouve dans [`experiments/`](experiments/README.md).
Elle documente et permet de lancer séparément toutes les phases du mémoire :

- phase A : baseline, commande adaptative et campagne statistique ;
- phase B : réseau saturé sans puis avec QoS SDN ;
- phase C : boucle fermée SUMO → orchestrateur → Ryu → OpenFlow ;
- phase D : rapport consolidé.

```bash
cd experiments
make build
make test
make smoke
make all-tests
```

Les détails des composants et des échanges sont présentés dans
[`experiments/ARCHITECTURE.md`](experiments/ARCHITECTURE.md).

Le rapport des tests effectivement exécutés est disponible dans
[`experiments/VALIDATION.md`](experiments/VALIDATION.md).

Les résultats sont produits localement dans `experiments/results_docker/` et ne
sont pas versionnés. Les prérequis et limites expérimentales, notamment la portée
de l’émulation Wi-Fi, sont détaillés dans le README du dossier.

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
