# Architecture du banc expérimental

## Composants

| Composant | Responsabilité |
|---|---|
| SUMO | Génération de la mobilité et des files au carrefour J1 |
| Orchestrateur TraCI | Choix adaptatif des phases NS/EW et publication des métriques |
| Ryu | API REST, hystérésis et installation des règles OpenFlow 1.3 |
| Open vSwitch | Commutation et sélection de la file prioritaire |
| HTB/netem | Limitation de capacité et délai du lien vers `edge` |
| iperf2 | Génération et mesure des flux réseau |

## Flux de décision

```text
SUMO --TraCI--> orchestrateur --HTTP /metrics--> Ryu
  ^                                             |
  |                                             v
phases TLS                              règle OpenFlow/QoS
                                                |
                                                v
véhicules/namespaces --------UDP----------> OVS/HTB --------> edge
```

Le seuil d’activation est `busy >= 8` et celui de désactivation `busy <= 3`.
L’hystérésis évite les basculements rapides. Le trafic de contrôle UDP/9999 est
dirigé vers la file 1 uniquement sur le port goulot `ap1-edge`.

## Isolation et reproductibilité

Ryu reste sous Python 3.9 en raison de ses contraintes de compatibilité. Toutes
les versions nécessaires sont installées dans l’image Docker. Les sorties sont
montées dans `results_docker/` et exclues du dépôt.

Les tests réseau demandent `/dev/net/tun` ainsi que les capacités `NET_ADMIN`,
`NET_RAW` et `SYS_ADMIN`. La CI exécute la construction et les tests unitaires ;
les scénarios réseau privilégiés restent à lancer sur un hôte Linux compatible.
