# Banc expérimental — mémoire 3

Ce dossier est le point d’entrée unique de tous les tests du mémoire. Toutes les commandes ci-dessous se lancent depuis ce dossier et écrivent leurs résultats dans `results_docker/`. Le scénario combine SUMO/TraCI, l’orchestrateur de feux, Ryu/OpenFlow, Open vSwitch, HTB et des véhicules représentés par des namespaces.

Voir aussi [ARCHITECTURE.md](ARCHITECTURE.md) pour le rôle des composants et les flux de décision.

Les dernières mesures réellement exécutées, ainsi que leurs limites d’interprétation, sont consignées dans [VALIDATION.md](VALIDATION.md).

## 1. Prérequis et préparation

- Linux avec `/dev/net/tun` ;
- Docker et le plugin `docker compose` ;
- autorisation de lancer les capacités `NET_ADMIN`, `NET_RAW` et `SYS_ADMIN`.

```bash
cd memoire_3/experiments/experiments
make build
make test
```

`make test` exécute les tests unitaires des analyseurs SUMO/iperf et du parseur de graines. `make smoke` contrôle rapidement Ryu, REST, OVS, OpenFlow, HTB, la connectivité, le trafic UDP et l’hystérésis.

## 2. Matrice complète des phases

| Phase | Test | Scénario | Commande individuelle | Sortie principale |
|---|---|---|---|---|
| A | A1 | Trafic asymétrique, feux fixes | `make test-a1` | `a1-baseline.json` |
| A | A2 | Trafic asymétrique, feux adaptatifs | `make test-a2` | `a2-adaptive.json` |
| A | A3 | Comparaison appariée A1/A2 | `make test-a3` | `evaluation.json` |
| A | A4 | Robustesse sur 30 graines | `make evaluate-30` | `evaluation-30.json` |
| B | B1 | Réseau saturé sans priorité | `make test-b1` | `ctrl_noqos.json` |
| B | B2 | Réseau saturé avec QoS SDN | `make test-b2` | `ctrl_qos.json` |
| B | B3 | Comparaison réseau B1/B2 | `make test-b3` | les deux JSON/CSV |
| C | C1 | Boucle fermée intégrée | `make test-c` | journaux SUMO/Ryu/orchestrateur |
| D | D1 | Rapport consolidé | `make test-d` | `report.md` |

Toute la suite se lance avec `make all-tests`.

## 3. Phase A — mobilité et commande des feux

`routes_asymmetric.rou.xml` injecte 1 300 véhicules en deux périodes : de 0 à 600 s, demande Nord–Sud forte et Est–Ouest faible ; de 600 à 1 200 s, demande Est–Ouest forte et Nord–Sud faible.

### A1 — baseline à feux fixes

```bash
make test-a1
```

Le contrôleur SUMO fixe reste inchangé. Le test mesure véhicules terminés et bloqués, complétion, durée, attente et temps perdu. Résultat attendu : complétion inférieure à 100 % sous cette charge.

### A2 — feux adaptatifs

```bash
make test-a2
```

Même trafic et même graine, avec phases NS=0 et EW=2, vert minimal 10 s, maximal 45 s et hystérésis 15 %. Le journal doit contenir `Switch ->` et la complétion doit dépasser A1.

### A3 — comparaison appariée rapide

```bash
make test-a3
```

A1 et A2 sont rejoués avec la graine 42. `evaluation.json` contient les deux séries et le gain de complétion. Une observation sert au contrôle fonctionnel, pas à une conclusion statistique.

### A4 — robustesse statistique

```bash
make evaluate-30
```

Les variantes sont appariées sur les graines `42,1..29`. Le rapport conserve 30 exécutions, moyennes et intervalles de confiance à 95 %. C’est la commande destinée aux valeurs finales du mémoire.

## 4. Phase B — réseau saturé et QoS SDN

Le lien vers `edge` est limité à 5 Mbit/s et retardé de 5 ms. `car2` et `car3` injectent chacun 8 Mbit/s pendant que `car1` émet le contrôle UDP/9999 à 1 Mbit/s : la charge dépasse volontairement la capacité.

### B1 — sans QoS

```bash
make test-b1
```

Ryu et OVS fonctionnent, mais `priority_enabled` reste faux. Sorties : `ctrl_noqos.json`, `ctrl_noqos.csv` et journaux iperf.

### B2 — avec QoS

```bash
make test-b2
```

Une métrique `busy=20` active Ryu. Le test vérifie REST, installe `set_queue:1` sur le port goulot et reproduit la même charge.

### B3 — comparaison réseau

```bash
make test-b3
```

Cette cible exécute B1 puis B2. Comparer les champs `summary` de `ctrl_noqos.json` et `ctrl_qos.json`. Les journaux clients donnent le débit émis ; iperf2 ne fournit jitter/pertes que côté serveur. Les compteurs OpenFlow et HTB constituent les preuves complémentaires de passage dans la file.

## 5. Phase C — boucle fermée intégrée

```bash
make test-c
```

Chaîne exécutée :

```text
SUMO -> files de véhicules -> orchestrateur -> POST /metrics
     -> Ryu -> règle OpenFlow set_queue:1 -> OVS/HTB
```

Le test réussit seulement si l’orchestrateur change de phase et si Ryu journalise l’installation de la règle. Artefacts : `tripinfo_closed_loop.xml`, `sumo_closed_loop.log`, `orchestrator_closed_loop.log` et `ryu.log`.

## 6. Phase D — rapport final

```bash
make test-d
```

Cette cible rejoue A3, B1, B2 et C1, puis génère `results_docker/report.md`. Pour le rapport statistique définitif, lancer également `make evaluate-30` et exploiter `evaluation-30.json`.

## 7. Paramétrage, validation globale et nettoyage

```bash
BW_EDGE=3 DELAY_EDGE=20ms make test-b2
make all-tests
make clean
```

Les résultats sont ignorés par Git mais restent disponibles dans `results_docker/`.

## 8. Limites expérimentales

Docker valide la mobilité, la décision adaptative, REST, Ryu, OpenFlow, OVS, HTB et les flux réseau virtuels. Les namespaces remplacent les stations Wi-Fi. Propagation 802.11, handovers et interférences exigent Mininet-WiFi avec `mac80211_hwsim` sur un hôte Linux et ne doivent pas être présentés comme mesurés par ce banc Docker.
