# Traffic Congestion Management with Connected Traffic Lights based on SDN

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

Les résultats sont produits localement dans `experiments/results_docker/` et ne
sont pas versionnés. Les prérequis et limites expérimentales, notamment la portée
de l’émulation Wi-Fi, sont détaillés dans le README du dossier.

## Implémentation historique

Le dossier `Achi Master Project/` conserve les scripts, documents et résultats de
l’implémentation initiale. Pour toute nouvelle reproduction, utiliser en priorité
le banc conteneurisé sous `experiments/`.
