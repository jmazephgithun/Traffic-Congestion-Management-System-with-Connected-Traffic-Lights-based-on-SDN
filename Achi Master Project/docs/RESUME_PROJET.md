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
- **Liens** : lien edge AP1<->edge limite a **5 Mbit/s** (`--bw-edge 5`) pour creer la congestion
- **QoS** : queues HTB sur les ports OVS (queue 0 = best-effort, queue 1 = priorite)
- **Correctif critique** : OVS noyau bypass `tc` htb → la limite de bande passante doit etre appliquee via `ovs-vsctl set port ... qos=...` (QoS native OVS), pas via TCLink

---

## 3. Ce qu'on veut prouver

### Preuve A : Benefice trafic (SUMO) — Resultats obtenus

> L'orchestrateur adaptatif fait passer 100% des vehicules la ou le baseline en bloque 25%.

| Metrique | Feux fixes (baseline) | Adaptatif (orchestrateur) | Resultat |
|----------|----------------------|--------------------------|---------|
| **Vehicules termines** | **974 / 1300 (74.9%)** | **1300 / 1300 (100%)** | **+326 vehicules (+33%)** |
| Temps d'attente moyen | ~82 s | ~82 s | Similaire (biais du survivant*) |
| Throughput | ~974 veh/h | ~977 veh/h | Similaire* |

*Le baseline ne mesure que les 974 vehicules qui ont reussi a passer. Les 326 bloques sont exclus des moyennes (biais du survivant). Le vrai gain est le **taux de completion : 75% → 100%**.

**Scenario utilise** : trafic asymetrique 1300 vehicules (`routes_asymmetric.rou.xml`).

### Preuve B : Benefice reseau (Mininet-WiFi + Ryu) — Resultats obtenus

> La QoS SDN reduit la perte de 68% a 0% et le jitter de 81 ms a 0.07 ms.

| Metrique | Sans QoS (B1) | Avec QoS (B2) | Amelioration |
|----------|---------------|---------------|--------------|
| **Perte paquets moyenne** | **68.55%** | **0.0%** | **-100%** |
| Perte paquets p95 | 88.3% | 0.0% | -100% |
| **Jitter moyen** | **81.34 ms** | **0.07 ms** | **x1162** |
| Jitter p95 | 184.18 ms | 0.12 ms | x1535 |
| Debit controle recu | 0.063 Mbit/s (31%) | 0.205 Mbit/s (100%) | x3.3 |

**Condition** : lien edge sature a 3.2x sa capacite (16 Mbit/s background sur lien 5 Mbit/s).
**Trafic controle** : UDP:9999, 200 Kbit/s. Ryu installe `set_queue:1` pour ce flux quand `busy >= 8`.

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
/home/jmazeph/experiments/
|
|-- pyfilesTrue/                         <- Code source Python
|   |-- tls_orchestrator_CORRECTED.py    <- Orchestrateur adaptatif (TraCI + REST)
|   |-- ryu_qos_rest.py                  <- Controleur Ryu SDN (QoS REST, port UDP=9999)
|   |-- traffic_topology_corridor.py     <- Topologie Mininet-WiFi (OVS QoS native)
|
|-- sumo_one_junction/                   <- Simulation SUMO
|   |-- one_junction.net.xml             <- Reseau routier (1 carrefour, 4 approches)
|   |-- one_junction.add.xml             <- Feux tricolores (4 phases)
|   |-- routes_asymmetric.rou.xml        <- 1300 veh asymetriques (scenario principal)
|   |-- one_junction_asymmetric.sumocfg  <- Config SUMO asymetrique
|
|-- scripts/                             <- Scripts de lancement
|   |-- LANCER_BASELINE_ASYMMETRIC.sh    <- Baseline feux fixes, 1300 veh
|   |-- LANCER_ADAPTIVE_ASYMMETRIC.sh    <- Adaptatif orchestrateur, 1300 veh
|   |-- COMPARER_ASYMMETRIC.sh           <- Comparaison baseline vs adaptive
|   |-- force_qos_on.sh                  <- Active la QoS Ryu manuellement
|
|-- tools/                               <- Outils d'analyse
|   |-- analyze_sumo.py                  <- tripinfo.xml -> KPI mobilite (JSON)
|   |-- analyze_iperf.py                 <- logs iperf2 -> KPI reseau (JSON/CSV)
|   |-- merge_report.py                  <- KPI mobilite + reseau -> rapport Markdown
|
|-- ctrl_no_qos/                         <- Resultats Phase B (reseau)
|   |-- ctrl_server_noqos.log            <- Log iperf serveur B1 (sans QoS)
|   |-- ctrl_noqos.json                  <- KPI B1 (68% perte, 81ms jitter)
|   |-- ctrl_server_qos.log              <- Log iperf serveur B2 (avec QoS)
|   |-- ctrl_qos.json                    <- KPI B2 (0% perte, 0.07ms jitter)
|
|-- results/                             <- Resultats Phase A (mobilite) et Phase D
    |-- tripinfo_baseline_asym.xml        <- Donnees brutes baseline
    |-- tripinfo_adaptive_asym.xml        <- Donnees brutes adaptive
    |-- sumo_baseline_asym.json           <- KPI mobilite baseline (974/1300)
    |-- sumo_adaptive_asym.json           <- KPI mobilite adaptive (1300/1300)
    |-- report.md                         <- Rapport fusionne final
```

---

## 6. Scenarios de test

### Scenario A : Trafic asymetrique (benefice orchestrateur)

Le fichier `routes_asymmetric.rou.xml` cree **1300 vehicules** en deux phases :

- **Phase 1 (0-600s)** : NS fort (500 veh), EW faible (150 veh)
- **Phase 2 (600-1200s)** : EW fort (500 veh), NS faible (150 veh)
- Total : 1300 vehicules

Avec les feux fixes (31s/31s), le vert est gaspille sur la direction vide → 326 vehicules bloques. L'orchestrateur adaptatif bascule le feu vers la direction chargee → 100% completion.

### Scenario B : Reseau sature (benefice QoS SDN)

La topologie Mininet-WiFi est lancee avec le **lien edge a 5 Mbit/s** (`--bw-edge 5`). Toutes les voitures sont proches d'AP1 → tout le trafic passe par ap1-eth3 vers edge.

- car2 + car3 envoient **16 Mbit/s** (8M chacun) → congestion 3.2x la capacite
- car1 envoie le flux de controle UDP:9999 a 200 Kbit/s
- **Sans QoS** : 68% perte, 81ms jitter, seulement 31% du debit cible recu
- **Avec QoS** : Ryu installe `set_queue:1` → 0% perte, 0.07ms jitter, 100% debit

**Correctif technique** : OVS noyau bypass `tc` htb. La limite de bande passante est appliquee via QoS native OVS (`ovs-vsctl set port ap1-eth3 qos=...`), pas via TCLink.

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
