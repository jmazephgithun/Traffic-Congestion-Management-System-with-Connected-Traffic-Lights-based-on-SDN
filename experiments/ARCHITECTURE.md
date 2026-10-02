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

## Niveau 1 : flux de décision du mémoire

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

En phase B, `car2` et `car3` émettent chacun 8 Mbit/s vers `edge` pendant que
`car1` émet le flux de contrôle à 200 kbit/s ; le lien `ap1-edge` est limité à
5 Mbit/s. Le jitter et les pertes du flux de contrôle sont lus dans le journal du
récepteur (`edge`), seul endroit où iperf2 les calcule.

## Niveau 2 : contrôleurs par secteur avec secours

Prototype de la proposition de déploiement du chapitre 3 (section 7), lancé par
`make test-secteurs`.

```text
              Abidjan Nord                              Abidjan Sud
   Ryu Nord 1 (6653/8080)  Ryu Nord 2 (6654/8081)   Ryu Sud 1 (6655/8082)  Ryu Sud 2 (6656/8083)
          principal               secours                 principal              secours
               \                 /                            \                 /
                \  OpenFlow 1.3 /                              \  OpenFlow 1.3 /
                 +-- apnord --+                                  +-- apsud ---+
                 |  fail_mode |                                  |  fail_mode |
                 | standalone |                                  | standalone |
                 +------------+                                  +------------+
              ncar1 ncar2 ncar3 nedge                         scar1 scar2 scar3 sedge
```

- Chaque pont est connecté en permanence à ses deux contrôleurs ; une sonde
  d’inactivité d’une seconde détecte la perte de l’un d’eux.
- L’orchestrateur publie ses métriques au principal et retombe sur le secours
  dès que le principal ne répond plus ; le secours installe alors la règle de
  priorité.
- Si les deux contrôleurs d’un secteur tombent, le pont passe en mode autonome
  (`fail_mode=standalone`) : l’acheminement continue, sans priorisation.
- Les deux secteurs sont indépendants : la panne du Nord ne touche pas le Sud.

## Isolation et reproductibilité

Ryu reste sous Python 3.9 en raison de ses contraintes de compatibilité. Toutes
les versions nécessaires sont installées dans l’image Docker. Les sorties sont
montées dans `results_docker/` et exclues du dépôt.

Les tests réseau demandent `/dev/net/tun` ainsi que les capacités `NET_ADMIN`,
`NET_RAW` et `SYS_ADMIN`. La CI exécute la construction, la vérification des
scripts et les tests unitaires ; les scénarios réseau privilégiés se lancent sur
un hôte Linux compatible.
