# Systeme de Gestion des Embouteillages avec des Feux Tricolores Connectes base sur SDN

## Memoire de Master - Resume du Projet

---

## 1. Objectif du memoire

Ce projet demontre qu'un **controleur SDN (Software-Defined Networking)** peut ameliorer la gestion du trafic routier en combinant deux niveaux d'intelligence :

- **Niveau trafic** : un orchestrateur adapte les feux tricolores en temps reel selon la congestion observee (via SUMO/TraCI).
- **Niveau reseau** : un controleur SDN (Ryu) priorise dynamiquement les messages de controle sur le reseau vehiculaire pour garantir qu'ils arrivent a temps, meme quand le reseau est sature.

L'idee centrale : **il ne suffit pas d'avoir un bon algorithme de feux ; il faut aussi que les messages de controle arrivent vite et sans perte**. C'est la que le SDN intervient.

---

## 2. Architecture du systeme

Le systeme repose sur **deux cerveaux** qui cooperent :

```
+------------------+         REST (busy)        +------------------+
|                  | --------------------------> |                  |
|   CERVEAU TRAFIC |                             |  CERVEAU RESEAU  |
|   (Orchestrateur |                             |  (Ryu SDN)       |
|    SUMO/TraCI)   |                             |                  |
|                  |                             |  - QoS (queues)  |
|  - Compte files  |                             |  - Priorite      |
|  - Change phases |                             |  - Re-routage    |
+------------------+                             +------------------+
        |                                                |
        v                                                v
+------------------+                             +------------------+
|                  |                             |                  |
|   SUMO           |                             |  Mininet-WiFi    |
|   (simulation    |                             |  (reseau emule)  |
|    trafic)       |                             |  AP1 <-> AP2     |
|                  |                             |  car1, car2, car3|
+------------------+                             +------------------+
```

### Cerveau Trafic (Orchestrateur)

- **Outil** : `tls_orchestrator_CORRECTED.py` connecte a SUMO via TraCI
- **Entree** : nombre de vehicules en file d'attente sur chaque approche (NS, EW)
- **Decision** : si une direction a beaucoup plus de vehicules, basculer le feu vert vers elle
- **Sortie** : commande `setPhase()` vers SUMO + POST `busy` vers Ryu
- **Parametres** : min_green=10s, max_green=45s, hysteresis=15%

### Cerveau Reseau (Ryu SDN)

- **Outil** : `ryu_qos_rest.py` (application Ryu, OpenFlow 1.3)
- **Entree** : metrique `busy` envoyee par l'orchestrateur via REST
- **Decision** : si busy >= 8 (carrefour charge), activer la priorite QoS
- **Action** : installer une regle OpenFlow `match UDP:9999 -> set_queue:1` sur tous les AP
- **Effet** : les paquets de controle passent dans une queue prioritaire, le trafic de fond est limite

### Reseau emule (Mininet-WiFi)

- **Outil** : `traffic_topology_corridor.py`
- **Topologie** : 2 AP (OVS), 3 stations (voitures), 1 serveur edge
- **Liens** : backhaul AP1-AP2 (configurable : 10 Mbit/s pour creer la congestion)
- **QoS** : queues HTB sur les ports OVS (queue 0 = best-effort, queue 1 = priorite)

---

## 3. Ce qu'on veut prouver

### Preuve A : Benefice trafic (SUMO)

> L'orchestrateur adaptatif reduit le temps d'attente par rapport aux feux fixes.

| Metrique | Feux fixes (baseline) | Adaptatif (orchestrateur) | Attendu |
|----------|----------------------|--------------------------|---------|
| Temps d'attente moyen | Eleve (feux gaspillent du vert sur direction vide) | Reduit (plus de vert pour la direction chargee) | -15 a -30% |
| Temps perdu moyen | Eleve | Reduit | -10 a -25% |
| Throughput (veh/h) | Reference | Maintenu ou ameliore | >= 95% baseline |

**Condition** : le scenario de trafic doit etre **asymetrique** (plus de vehicules NS que EW, ou demande variable dans le temps). Avec un trafic symetrique, les feux fixes sont deja optimaux.

### Preuve B : Benefice reseau (Mininet-WiFi + Ryu)

> Le SDN protege les messages de controle quand le reseau est sature.

| Metrique | Sans QoS | Avec QoS (SDN) | Attendu |
|----------|----------|----------------|---------|
| Jitter moyen (ms) | Eleve (5-50 ms) | Faible (< 1 ms) | Reduction significative |
| Perte de paquets (%) | Significative (10-40%) | Tres faible (< 5%) | Reduction significative |
| Bande passante ctrl | Instable | Stable ~200 Kbit/s | Stabilisation |

**Condition** : le lien reseau doit etre **sature** (trafic de fond > capacite du lien). Sans congestion, la QoS n'a rien a proteger.

### Preuve C : Boucle fermee (systeme integre)

> Quand le carrefour est charge, l'orchestrateur previent Ryu, qui active la QoS en temps reel.

C'est la demonstration complete du titre du memoire : l'orchestrateur gere les embouteillages, les feux sont connectes via le reseau, et le SDN garantit que les communications restent fiables.

---

## 4. Outils utilises

| Outil | Role | Version |
|-------|------|---------|
| **SUMO** | Simulation microscopique du trafic routier | 1.x |
| **TraCI** | API Python pour controler SUMO en temps reel | (inclus dans SUMO) |
| **Ryu** | Controleur SDN (OpenFlow 1.3) | 4.x |
| **Mininet-WiFi** | Emulation de reseau sans-fil avec OVS | 2.x |
| **Open vSwitch (OVS)** | Switch virtuel OpenFlow avec queues QoS | 2.x |
| **iperf2** | Generation et mesure de trafic reseau (UDP) | 2.x |
| **Python 3** | Langage pour l'orchestrateur, analyses, topologie | 3.8+ |

---

## 5. Structure des fichiers

```
~/experiments/
|
|-- Fichiers principaux
|   |-- tls_orchestrator_CORRECTED.py    <- Orchestrateur adaptatif (TraCI + REST)
|   |-- ryu_qos_rest.py                  <- Controleur Ryu SDN (QoS REST)
|   |-- traffic_topology_corridor.py     <- Topologie Mininet-WiFi
|
|-- Simulation SUMO
|   |-- sumo_one_junction/
|       |-- one_junction.net.xml         <- Reseau routier (1 carrefour, 4 approches)
|       |-- one_junction.add.xml         <- Feux tricolores (4 phases : GGrr, yyrr, rrGG, rryy)
|       |-- locked.rou.xml               <- Routes symetriques (928 veh, 232 par direction)
|       |-- routes_asymmetric.rou.xml    <- Routes asymetriques (NS fort puis EW fort)
|       |-- one_junction.sumocfg         <- Config SUMO (routes symetriques)
|       |-- one_junction_asymmetric.sumocfg <- Config SUMO (routes asymetriques)
|
|-- Scripts de lancement
|   |-- LANCER_BASELINE_ASYMMETRIC.sh    <- Test feux fixes, trafic asymetrique
|   |-- LANCER_ADAPTIVE_ASYMMETRIC.sh    <- Test adaptatif, trafic asymetrique
|   |-- COMPARER_ASYMMETRIC.sh           <- Comparaison baseline vs adaptive
|   |-- force_qos_on.sh                  <- Active la QoS manuellement (sans SUMO)
|
|-- Outils d'analyse
|   |-- tools/
|       |-- analyze_sumo.py              <- Analyse tripinfo.xml -> KPI mobilite (JSON)
|       |-- analyze_iperf.py             <- Analyse logs iperf2 -> KPI reseau (JSON)
|       |-- merge_report.py              <- Fusionne KPI mobilite + reseau -> rapport Markdown
|
|-- Resultats
    |-- results/
        |-- tripinfo_baseline.xml        <- Donnees brutes baseline
        |-- tripinfo_adaptive.xml        <- Donnees brutes adaptive
        |-- sumo_baseline.json           <- KPI mobilite baseline
        |-- sumo_adaptive.json           <- KPI mobilite adaptive
        |-- ctrl_noqos.json              <- KPI reseau sans QoS
        |-- ctrl_qos.json                <- KPI reseau avec QoS
        |-- report.md                    <- Rapport fusionne final
```

---

## 6. Scenarios de test

### Scenario A : Trafic asymetrique (benefice orchestrateur)

Le fichier `routes_asymmetric.rou.xml` cree un trafic en deux phases :

- **Phase 1 (0-600s)** : NS fort (500 veh), EW faible (150 veh)
- **Phase 2 (600-1200s)** : EW fort (500 veh), NS faible (150 veh)

Avec les feux fixes (31s/31s), le vert est gaspille sur la direction vide. L'orchestrateur adaptatif donne plus de vert a la direction chargee.

### Scenario B : Reseau sature (benefice QoS SDN)

La topologie Mininet-WiFi est lancee avec un backhaul de **10 Mbit/s**. Le trafic de fond (car2 + car3) envoie **16 Mbit/s** (8M chacun), ce qui sature le lien. Le flux de controle (car1, UDP:9999, 200 Kbit/s) est noye dans la congestion.

- **Sans QoS** : le flux de controle subit du jitter et des pertes.
- **Avec QoS** : Ryu installe `set_queue:1` pour UDP:9999, le flux est protege.

### Scenario C : Boucle fermee (test integre)

SUMO + orchestrateur + Ryu + Mininet-WiFi tournent ensemble en **temps reel** (option `--realtime`). L'orchestrateur poste les metriques a Ryu, qui active/desactive la QoS dynamiquement selon la congestion du carrefour.

---

## 7. Metriques collectees

### Mobilite (SUMO)

| Metrique | Source | Unite |
|----------|--------|-------|
| Nombre de vehicules termines | tripinfo.xml | veh |
| Duree moyenne de trajet | tripinfo.xml | s |
| Temps d'attente moyen | tripinfo.xml | s |
| Temps perdu moyen | tripinfo.xml | s |
| Throughput | calcule (veh / duree simulation) | veh/h |
| Vitesse moyenne | calcule (distance / duree) | m/s |

### Reseau (iperf2)

| Metrique | Source | Unite |
|----------|--------|-------|
| Jitter moyen | log serveur iperf2 | ms |
| Jitter P95 | log serveur iperf2 | ms |
| Perte de paquets moyenne | log serveur iperf2 | % |
| Bande passante moyenne | log serveur iperf2 | Mbit/s |

---

## 8. Lien avec le titre du memoire

**"Systeme de Gestion des Embouteillages avec des Feux Tricolores Connectes base sur SDN"**

- **Gestion des embouteillages** : l'orchestrateur SUMO adapte les feux pour reduire la congestion (Preuve A).
- **Feux tricolores connectes** : les feux et capteurs communiquent via un reseau vehiculaire emule par Mininet-WiFi.
- **Base sur SDN** : le controleur Ryu protege et route dynamiquement les communications de controle selon la congestion reelle (Preuve B). La boucle fermee relie les deux mondes (Preuve C).
