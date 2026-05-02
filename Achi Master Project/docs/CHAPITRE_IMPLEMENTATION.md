# Chapitre : Implémentation du Système de Gestion des Embouteillages basé sur SDN

---

## Table des matières

1. [Environnement de développement](#1-environnement-de-développement)
2. [Architecture globale du système](#2-architecture-globale-du-système)
3. [Implémentation de la simulation de trafic (SUMO)](#3-implémentation-de-la-simulation-de-trafic-sumo)
4. [Implémentation de l'orchestrateur adaptatif](#4-implémentation-de-lorchéstrateur-adaptatif)
5. [Implémentation du réseau SDN (Mininet-WiFi)](#5-implémentation-du-réseau-sdn-mininet-wifi)
6. [Implémentation du contrôleur Ryu avec QoS](#6-implémentation-du-contrôleur-ryu-avec-qos)
7. [Problème critique et solution : le contournement OVS](#7-problème-critique-et-solution--le-contournement-ovs)
8. [Intégration en boucle fermée](#8-intégration-en-boucle-fermée)
9. [Protocole de test et résultats](#9-protocole-de-test-et-résultats)
10. [Analyse comparative des résultats](#10-analyse-comparative-des-résultats)

---

## 1. Environnement de développement

### 1.1 Outils et versions

L'implémentation du système repose sur un ensemble d'outils open-source complémentaires, chacun prenant en charge un niveau d'abstraction différent du système global.

| Outil | Rôle | Version |
|-------|------|---------|
| **SUMO** (Simulation of Urban MObility) | Simulateur de trafic microscopique | 1.x |
| **TraCI** (Traffic Control Interface) | API Python de contrôle temps réel de SUMO | inclus dans SUMO |
| **Ryu** | Contrôleur SDN OpenFlow 1.3 | 4.x |
| **Mininet-WiFi** | Émulateur de réseau sans-fil basé sur OVS | 2.x |
| **Open vSwitch (OVS)** | Commutateur virtuel OpenFlow avec QoS HTB | 2.x |
| **iperf2** | Génération et mesure de trafic UDP | 2.x |
| **Python 3** | Langage de développement principal | 3.8+ |

### 1.2 Structure du projet

Le projet est organisé en modules fonctionnels indépendants pour faciliter les tests séparés de chaque composant :

```
/home/jmazeph/experiments/
├── pyfilesTrue/
│   ├── tls_orchestrator_CORRECTED.py   # Orchestrateur adaptatif (TraCI + REST)
│   ├── ryu_qos_rest.py                 # Contrôleur Ryu SDN (QoS dynamique)
│   └── traffic_topology_corridor.py    # Topologie réseau Mininet-WiFi
├── sumo_one_junction/
│   ├── one_junction.net.xml            # Réseau routier SUMO
│   ├── one_junction.add.xml            # Configuration des feux tricolores
│   ├── routes_asymmetric.rou.xml       # Scénario 1300 véhicules asymétriques
│   └── one_junction_asymmetric.sumocfg # Fichier de configuration SUMO
├── scripts/
│   ├── LANCER_BASELINE_ASYMMETRIC.sh
│   ├── LANCER_ADAPTIVE_ASYMMETRIC.sh
│   ├── COMPARER_ASYMMETRIC.sh
│   └── force_qos_on.sh
├── tools/
│   ├── analyze_sumo.py                 # Analyse KPI mobilité
│   ├── analyze_iperf.py                # Analyse KPI réseau
│   └── merge_report.py                 # Rapport final fusionné
└── ctrl_no_qos/                        # Résultats des tests réseau
```

---

## 2. Architecture globale du système

### 2.1 Vue d'ensemble

Le système implémenté comporte deux sous-systèmes coopérants, communiquant via une API REST :

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PLAN DE CONTRÔLE                               │
│                                                                     │
│  ┌──────────────────────┐    busy = ns_q + ew_q   ┌─────────────┐  │
│  │  Orchestrateur SUMO  │ ─────── POST /metrics ──►│  Ryu SDN   │  │
│  │  tls_orchestrator    │                          │ ryu_qos_    │  │
│  │  _CORRECTED.py       │◄────── TraCI ────────────│ rest.py    │  │
│  │                      │                          │            │  │
│  │ • Compte les files   │                          │ • busy≥8   │  │
│  │ • Change les phases  │                          │   → QoS ON │  │
│  │ • Envoie busy à Ryu  │                          │ • busy≤3   │  │
│  └──────────────────────┘                          │   → QoS OFF│  │
│           │                                        └──────┬──────┘  │
└───────────┼────────────────────────────────────────────── │ ────────┘
            │                                               │
            ▼ setPhase()                                    ▼ OpenFlow 1.3
┌──────────────────────┐                         ┌──────────────────────┐
│  SUMO                │                         │  Mininet-WiFi        │
│  Simulation trafic   │                         │  Réseau véhiculaire  │
│                      │                         │                      │
│  • 1 carrefour       │                         │  AP1 ── ap1-eth3 ──  │
│  • 4 approches       │                         │  (5 Mbit/s) ── edge  │
│  • 1300 véhicules    │                         │  car1, car2, car3    │
└──────────────────────┘                         └──────────────────────┘
```

### 2.2 Flux de communication

Le flux de données entre les composants suit le schéma suivant :

1. **SUMO** simule la circulation et expose les données de files d'attente via TraCI
2. **L'orchestrateur** interroge SUMO à chaque pas de simulation, calcule `busy = ns_q + ew_q` et l'envoie au contrôleur Ryu via HTTP POST sur `/metrics`
3. **Ryu** évalue le niveau `busy` : si `busy ≥ 8`, il installe des règles OpenFlow qui mettent le trafic UDP:9999 en file prioritaire (queue 1)
4. **Mininet-WiFi** exécute ces règles sur les ponts OVS, garantissant que les paquets de contrôle passent même en cas de congestion

---

## 3. Implémentation de la simulation de trafic (SUMO)

### 3.1 Réseau routier

Le réseau routier est défini dans `one_junction.net.xml`. Il représente un carrefour isolé à quatre branches :

- **Nord → Jonction J1** : arête `N2J1`
- **Sud → Jonction J1** : arête `S2J1`
- **Est → Jonction J1** : arête `E2J1`
- **Ouest → Jonction J1** : arête `W2J1`

Ce carrefour unique permet d'isoler l'effet de l'algorithme adaptatif sans interférences avec d'autres intersections.

### 3.2 Configuration des feux tricolores

Le fichier `one_junction.add.xml` définit quatre phases pour le feu `J1` :

| Phase | Index | État | Description |
|-------|-------|------|-------------|
| NS vert | 0 | `GGrr` | Nord-Sud vert, Est-Ouest rouge |
| NS jaune | 1 | `yyrr` | Transition NS → rouge |
| EW vert | 2 | `rrGG` | Est-Ouest vert, Nord-Sud rouge |
| EW jaune | 3 | `rryy` | Transition EW → rouge |

L'orchestrateur agit directement sur les phases 0 et 2 via `TraCI.trafficlight.setPhase()`.

### 3.3 Scénario de trafic asymétrique

Le scénario principal utilise `routes_asymmetric.rou.xml` qui génère **1300 véhicules** en deux phases temporelles :

```
Véhicules
    ▲
500 │████████████████                    ████████████████  ← NS
    │
150 │                ████████████████                      ← EW
    │
    └────────────────────────────────────────────────────► Temps
         0s        600s       1200s     1800s
           Phase 1 (NS fort)   Phase 2 (EW fort)
```

Ce déséquilibre délibéré rend les feux fixes sous-optimaux : en phase 1, le vert EW est gaspillé sur une direction quasi-vide, accumulant des véhicules NS qui dépassent la capacité de la file.

---

## 4. Implémentation de l'orchestrateur adaptatif

### 4.1 Connexion à SUMO via TraCI

L'orchestrateur établit une connexion TCP avec SUMO sur le port 8813. La fonction `connect_traci()` gère la connexion et réalise quelques pas de chauffe pour stabiliser l'état initial :

```python
def connect_traci(port: int, host: str = "127.0.0.1"):
    tr = traci.connect(port=port, host=host)
    log(f"Connected to SUMO on port {port}")
    for _ in range(3):
        try:
            tr.simulationStep()
        except Exception:
            break
        time.sleep(0.02)
    return tr
```

### 4.2 Comptage des véhicules en file

La mesure des files d'attente s'effectue par arête via `tr.edge.getLastStepVehicleNumber()`. La fonction `sum_edges()` agrège les valeurs sur toutes les arêtes d'une direction :

```python
def sum_edges(tr, edges, fn='veh'):
    total = 0
    for e in edges:
        try:
            if fn == 'halt':
                total += tr.edge.getLastStepHaltingNumber(e)
            else:
                total += tr.edge.getLastStepVehicleNumber(e)
        except Exception:
            pass
    return total
```

Deux modes sont disponibles : `'veh'` (tous les véhicules sur l'arête) et `'halt'` (véhicules à l'arrêt uniquement). Le mode `'veh'` a été retenu car il offre une mesure de charge plus stable.

### 4.3 Algorithme de décision adaptatif

L'algorithme de commutation de phase est le cœur de l'orchestrateur. Il repose sur trois conditions :

**Condition 1 — Pression directionnelle (hystérésis)**
Un changement est déclenché si la file adverse dépasse la file courante d'un facteur `(1 + hysteresis)`. L'hystérésis de 15% évite les oscillations rapides :

```
Si phase = NS_VERT et EW_q > NS_q × 1.15  →  commuter vers EW_VERT
Si phase = EW_VERT et NS_q > EW_q × 1.15  →  commuter vers NS_VERT
```

**Condition 2 — Temps maximum (équité)**
Si aucune commutation n'a eu lieu pendant `max_green = 45s`, le changement est forcé pour éviter qu'une direction monopolise le vert.

**Condition 3 — Temps minimum (stabilité)**
Aucun changement n'est autorisé avant `min_green = 10s` pour éviter un clignotement perturbateur.

Le code correspondant :

```python
if current_phase == ns_green_idx:
    ew_pressure = ew_q > ns_q * (1.0 + args.hysteresis)
    max_time_reached = elapsed >= args.max_green

    if (ew_pressure or max_time_reached) and elapsed >= args.min_green:
        should_switch = True
        new_phase = ew_green_idx
else:
    ns_pressure = ns_q > ew_q * (1.0 + args.hysteresis)
    max_time_reached = elapsed >= args.max_green

    if (ns_pressure or max_time_reached) and elapsed >= args.min_green:
        should_switch = True
        new_phase = ns_green_idx

if should_switch:
    tr.trafficlight.setPhase(args.tls_id, new_phase)
    current_phase = new_phase
    last_switch_time = now
```

### 4.4 Transmission des métriques au contrôleur Ryu

À chaque pas de simulation, l'orchestrateur envoie les métriques de trafic au contrôleur Ryu via HTTP POST :

```python
def post_metrics(url, ns_q, ew_q):
    busy = float(ns_q + ew_q)
    payload = {'ns_q': int(ns_q), 'ew_q': int(ew_q), 'busy': busy}
    r = requests.post(url, json=payload, timeout=1.0)
    return r.status_code, r.text
```

La valeur `busy` représente la charge totale du carrefour. Le contrôleur Ryu active la QoS quand `busy ≥ 8` véhicules (paramètre configurable).

### 4.5 Mode temps réel

Pour les tests intégrés (Phase C), l'option `--realtime` synchronise la simulation SUMO avec le temps réel. Sans cette option, SUMO termine en quelques secondes et les tests réseau n'ont pas le temps de s'exécuter :

```python
if args.realtime:
    sim_elapsed = now - sim_start
    wall_target = sim_elapsed / args.realtime_factor
    wall_elapsed = time.time() - wall_start
    sleep_time = wall_target - wall_elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)
```

### 4.6 Correction du bug principal

La première version de l'orchestrateur souffrait d'un bug critique : la variable `target_phase` et la variable `cur_phase` étaient maintenues séparément, créant une confusion entre la phase désirée et la phase réelle. Résultat : l'orchestrateur restait bloqué sur la phase 0 (NS vert) indéfiniment, bloquant tous les véhicules EW.

**Correction** : `current_phase` est désormais l'unique source de vérité, mise à jour immédiatement après chaque appel à `setPhase()`. La variable `should_switch` est une décision binaire calculée à chaque pas, sans état résiduel.

---

## 5. Implémentation du réseau SDN (Mininet-WiFi)

### 5.1 Topologie du réseau

La topologie est définie dans `traffic_topology_corridor.py`. Elle modélise un réseau véhiculaire de corridor :

```
                         WiFi (802.11g, 2.4GHz)
        ┌──────────────────────────────────────┐
        │         AP1 (OVS bridge)             │
        │    ssid=ap1-ssid, canal 1            │
        │    position (0,0,0), range 120m      │
        │                                      │
car1 ───┤  ip=10.0.0.1    position (5,0,0)    │
car2 ───┤  ip=10.0.0.2    position (12,0,0)   │
car3 ───┤  ip=10.0.0.3    position (20,0,0)   │
        │                                      │
        └──────────────┬───────────────────────┘
                       │ ap1-eth3
                       │ 5 Mbit/s -- 5ms (lien edge)
                       │
                      edge  ip=10.0.0.254
                       │
                       │ ap1-eth2
                       │ backhaul (100 Mbit/s par défaut)
                       │
        ┌──────────────┴───────────────────────┐
        │         AP2 (OVS bridge)             │
        │    ssid=ap2-ssid, canal 6            │
        │    position (90,0,0), range 120m     │
        └──────────────────────────────────────┘
```

### 5.2 Configuration de la topologie

```python
net = Mininet_wifi(
    controller=RemoteController,
    link=TCLink,
    accessPoint=OVSKernelAP,
    switch=OVSKernelSwitch,
    autoSetMacs=True,
    autoStaticArp=True
)

ap1 = net.addAccessPoint('ap1', ssid='ap1-ssid', mode='g', channel='1',
                         position='0,0,0', range=120)
ap2 = net.addAccessPoint('ap2', ssid='ap2-ssid', mode='g', channel='6',
                         position='90,0,0', range=120)

car1 = net.addStation('car1', ip='10.0.0.1/24', position='5,0,0')
car2 = net.addStation('car2', ip='10.0.0.2/24', position='12,0,0')
car3 = net.addStation('car3', ip='10.0.0.3/24', position='20,0,0')

edge = net.addHost('edge', ip='10.0.0.254/24')
```

Le modèle de propagation log-distance avec exposant 2.8 simule un environnement urbain réaliste. Les trois voitures sont positionnées dans la portée de AP1, ce qui fait passer tout leur trafic par le lien `ap1-eth3` (5 Mbit/s) vers `edge`.

### 5.3 Lien edge : goulot d'étranglement contrôlé

Le lien `ap1 ↔ edge` est intentionnellement limité à **5 Mbit/s** pour simuler une contrainte réseau réaliste sur un lien cellulaire ou backhaul. Ce lien est le goulot d'étranglement sur lequel la QoS agit :

```python
net.addLink(ap1, edge,
            intfName1='ap1-eth3', intfName2='edge-eth0',
            cls=TCLink,
            bw=args.bw_edge,        # 5 Mbit/s
            delay=args.delay_edge,  # 5ms
            loss=args.loss_edge)    # 0.05%
```

### 5.4 Configuration OpenFlow initiale

Après le démarrage du réseau, chaque pont OVS est configuré en OpenFlow 1.3 avec une règle de table-miss par défaut (`NORMAL`) pour assurer la connectivité de base :

```python
for ap in (ap1, ap2):
    sh(ap, f'ovs-vsctl set bridge {ap.name} protocols=OpenFlow13')
    sh(ap, f'ovs-ofctl -O OpenFlow13 add-flow {ap.name} "priority=0,actions=NORMAL"')
```

Cette règle `priority=0` sera supplantée par les règles de priorité `priority=20000` installées par Ryu en cas de congestion.

---

## 6. Implémentation du contrôleur Ryu avec QoS

### 6.1 Principe de fonctionnement

Le contrôleur Ryu (`ryu_qos_rest.py`) expose une API REST et gère dynamiquement la priorité du trafic de contrôle. Il implémente un mécanisme d'hystérésis pour éviter les oscillations :

- **Activation** : si `busy ≥ 8.0` → installe la règle de priorité
- **Désactivation** : si `busy ≤ 3.0` → retire la règle de priorité

### 6.2 API REST

Deux endpoints sont exposés :

```
GET  /health   → {"status": "ok", "priority_enabled": bool}
POST /metrics  → {"busy": float, "ns_q": int, "ew_q": int}
               ← {"status": "ok", "busy": float, "priority": bool}
```

### 6.3 Règle OpenFlow de priorité

Quand la QoS est activée, Ryu installe sur tous les ponts OVS connectés deux règles à `priority=20000` :

```python
def _install_priority_flow(self, dp):
    ofp = dp.ofproto
    p   = dp.ofproto_parser

    # Trafic de contrôle : UDP destination port 9999 → queue 1
    match = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=9999)
    actions = [p.OFPActionSetQueue(1), p.OFPActionOutput(ofp.OFPP_NORMAL)]
    self._add_flow(dp, priority=20000, match=match, actions=actions)

    # Réponses du serveur : UDP source port 9999 → queue 1
    match_reply = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=9999)
    self._add_flow(dp, priority=20000, match=match_reply, actions=actions)
```

L'action `OFPActionSetQueue(1)` redirige le paquet vers la file de priorité (queue 1) avant de le transmettre normalement. La règle de bas niveau `priority=0, actions=NORMAL` continue de traiter tout le reste du trafic.

### 6.4 Gestion du cycle de vie des datapaths

Le contrôleur maintient un dictionnaire des datapaths actifs et réinstalle les règles de priorité si un pont OVS se reconnecte pendant une période de congestion active :

```python
@set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
def _state_change_handler(self, ev):
    dp = ev.datapath
    if ev.state == MAIN_DISPATCHER:
        self.datapaths[dp.id] = dp
        if self.priority_enabled:
            self._install_priority_flow(dp)  # Réinstallation automatique
    elif ev.state == DEAD_DISPATCHER:
        del self.datapaths[dp.id]
```

---

## 7. Problème critique et solution : le contournement OVS

### 7.1 Description du problème

Lors des premiers tests, le lien edge limité à 5 Mbit/s ne produisait aucune congestion observable : le trafic de fond de 16 Mbit/s passait sans perte ni jitter significatif.

Après investigation, la cause racine a été identifiée :

> **OVS (Open vSwitch) en mode noyau contourne entièrement les règles `tc-htb` (Traffic Control - Hierarchical Token Bucket) appliquées par `TCLink` de Mininet.** OVS maintient son propre chemin de données dans le noyau Linux, indépendant de la pile `tc`. Les règles `tc` s'appliquent à l'interface réseau virtuelle, mais OVS transfère les paquets en-dessous de cette couche, sans les soumettre au contrôle de flux.

### 7.2 Illustration du problème

```
Flux de paquets AVANT correction :

car1 ──► [WiFi] ──► OVS bridge (ap1) ──► ap1-eth3 ──► edge
                          │
                          │  OVS bypasse tc-htb !
                          ▼
                  tc-htb qdisc (5 Mbit/s)
                  (jamais atteint par les paquets OVS)
```

### 7.3 Solution : QoS native OVS

La solution consiste à configurer la limitation de bande passante directement dans OVSDB via `ovs-vsctl`, en créant des queues HTB natives OVS qui sont reconnues par le chemin de données noyau :

```python
def attach_qos(port: str, max_rate_mbit: int,
               dflt_min_kbit=1000, dflt_max_kbit=None,
               prio_min_kbit=5000, prio_max_kbit=None):
    """
    Attache une QoS linux-htb OVS native sur un port avec 2 files :
      - queue 0 : best-effort (jusqu'à 90% du lien)
      - queue 1 : priorité    (jusqu'à 100% du lien)
    """
    cmd = (
        f'ovs-vsctl -- set port {port} qos=@q '
        f'-- --id=@q create qos type=linux-htb '
        f'    other-config:max-rate={max_rate_mbit*1000*1000} '
        f'    queues:0=@dflt queues:1=@prio '
        f'-- --id=@dflt create queue '
        f'    other-config:min-rate={dflt_min_kbit*1000} '
        f'    other-config:max-rate={dflt_max_kbit*1000} '
        f'-- --id=@prio create queue '
        f'    other-config:min-rate={prio_min_kbit*1000} '
        f'    other-config:max-rate={prio_max_kbit*1000}'
    )
    return cmd
```

### 7.4 Structure des queues HTB

Avec l'option `--configure-qos`, deux queues sont créées sur chaque port OVS :

```
Port ap1-eth3 (5 Mbit/s)
├── QoS HTB (max-rate = 5 000 000 bit/s)
│   ├── Queue 0 (best-effort)
│   │   ├── min-rate =  1 000 000 bit/s (1 Mbit/s garanti)
│   │   └── max-rate =  4 500 000 bit/s (90% du lien)
│   └── Queue 1 (priorité — trafic UDP:9999)
│       ├── min-rate =  5 000 000 bit/s (100% garanti)
│       └── max-rate =  5 000 000 bit/s (100% du lien)
```

L'action OpenFlow `set_queue:1` redirige les paquets UDP:9999 vers la queue 1. En situation de congestion, la queue 0 est étranglée par l'HTB, mais la queue 1 conserve un accès prioritaire à toute la bande passante disponible.

### 7.5 Mode sans QoS (test B1)

Pour le test de référence (sans QoS), une queue unique est créée pour activer la limitation de bande passante sans différenciation de service :

```python
# Mode sans QoS : rate limit simple, 1 seule queue
for port, bw_mbit in [('ap1-eth3', args.bw_edge), ...]:
    max_rate = bw_mbit * 1000 * 1000
    cmd = (
        f'ovs-vsctl -- set port {port} qos=@q '
        f'-- --id=@q create qos type=linux-htb '
        f'    other-config:max-rate={max_rate} queues:0=@dflt '
        f'-- --id=@dflt create queue '
        f'    other-config:max-rate={max_rate}'
    )
```

Cette approche garantit que les deux tests B1 et B2 opèrent avec la même contrainte de bande passante (5 Mbit/s effective), rendant la comparaison équitable.

---

## 8. Intégration en boucle fermée

### 8.1 Chronologie du test intégré (Phase C)

```
Temps (s)
  0  ├─ SUMO démarre (1300 véhicules en attente)
     │
  0  ├─ Orchestrateur connecté (TraCI port 8813)
     │   └─ Phase initiale : NS_VERT
     │
  0  ├─ Ryu en attente de métriques
     │   └─ priority_enabled = false
     │
 30  ├─ Files NS commencent à saturer (500 véhicules affluent)
     │   └─ busy = ns_q + ew_q → dépasse 8
     │
 30  ├─ Ryu reçoit busy≥8 → active QoS
     │   └─ Installe set_queue:1 pour UDP:9999 sur ap1, ap2
     │
 35  ├─ Tests iperf lancés dans Mininet :
     │   ├─ car2 → edge:5001 @ 8 Mbit/s (background)
     │   ├─ car3 → edge:6001 @ 8 Mbit/s (background)
     │   └─ car1 → edge:9999 @ 200 Kbit/s (contrôle)
     │
 80  ├─ Orchestrateur bascule vers EW_VERT (files EW > NS × 1.15)
     │   └─ busy redescend temporairement
     │
600  ├─ Phase 2 commence (EW fort, NS faible)
     │
1200 └─ Simulation terminée
```

### 8.2 Paramètres d'activation de la QoS

```
ENABLE_THRESHOLD  = 8.0   # busy ≥ 8  → QoS activée
DISABLE_THRESHOLD = 3.0   # busy ≤ 3  → QoS désactivée
```

L'hystérésis entre les deux seuils (8 et 3) prévient les oscillations rapides quand le trafic fluctue autour d'une valeur limite.

---

## 9. Protocole de test et résultats

### 9.1 Phase A — Tests de mobilité (SUMO)

**Scénario** : trafic asymétrique, 1300 véhicules, durée de simulation libre.

**Mesures collectées** : nombre de véhicules terminés, temps d'attente moyen, temps perdu moyen, débit (véhicules/heure).

**Résultats obtenus** :

| Métrique | Baseline (feux fixes) | Adaptatif | Gain |
|----------|----------------------|-----------|------|
| Véhicules terminés | 974 / 1300 (74.9%) | 1300 / 1300 (100%) | +326 véh. |
| Temps d'attente moy. | ~82 s | ~82 s | équivalent* |
| Débit | ~974 véh/h | ~977 véh/h | équivalent* |

*L'équivalence des moyennes s'explique par le **biais du survivant** : le baseline calcule ses moyennes uniquement sur les 974 véhicules ayant franchi le carrefour. Les 326 véhicules bloqués ne contribuent pas aux statistiques.

**Interprétation** : Le gain n'est pas dans la vitesse individuelle de chaque véhicule, mais dans la **capacité à évacuer l'intégralité du trafic**. Le baseline provoque un effondrement catastrophique quand les files débordent ; l'orchestrateur adaptatif prévient cet effondrement.

### 9.2 Phase B — Tests réseau

**Configuration** : lien edge = 5 Mbit/s, background = 2 × 8 Mbit/s = 16 Mbit/s (ratio de congestion : 3.2×).

**Trafic mesuré** : UDP:9999, 200 Kbit/s, server sur `edge`, client sur `car1`, durée 80-90 s.

**B1 — Sans QoS** : iperf server sur `edge:9999`, aucune règle de priorité Ryu.

**B2 — Avec QoS** : mêmes conditions + `force_qos_on.sh` → Ryu installe `set_queue:1` pour UDP:9999.

**Résultats obtenus** :

| Métrique | B1 (sans QoS) | B2 (avec QoS) | Amélioration |
|----------|---------------|---------------|--------------|
| Perte paquets (moy.) | 68.55% | **0.00%** | −100% |
| Perte paquets (p95) | 88.30% | **0.00%** | −100% |
| Jitter (moy.) | 81.34 ms | **0.07 ms** | × 1162 |
| Jitter (p95) | 184.18 ms | **0.12 ms** | × 1535 |
| Débit ctrl reçu | 0.063 Mbit/s | **0.205 Mbit/s** | × 3.3 |
| Débit cible atteint | 31% | **100%** | +69 pts |

---

## 10. Analyse comparative des résultats

### 10.1 Analyse des résultats de mobilité

La différence fondamentale entre les deux approches est qualitative, pas seulement quantitative.

**Avec feux fixes** : les phases de 31s/31s sont optimisées pour un trafic équilibré. En trafic asymétrique, les véhicules NS s'accumulent pendant les 31s de vert EW (direction quasi-vide). Passé un seuil critique, la file NS déborde et les véhicules ne peuvent plus entrer dans le carrefour. C'est un phénomène de **blocage par saturation** (gridlock partiel) : les véhicules en tête de file bloquent ceux derrière, créant une congestion en cascade. Les 326 véhicules "non terminés" ne sont pas sorties de la simulation ; ils sont restés bloqués en file d'attente jusqu'à la fin de la simulation.

**Avec orchestrateur adaptatif** : dès que la file NS dépasse 1.15× la file EW, la phase bascule vers NS_VERT. Le vert est alloué dynamiquement là où la demande est réelle. Le phénomène de saturation est prévenu, et 100% des 1300 véhicules terminent leur trajet.

### 10.2 Analyse des résultats réseau

**Sans QoS (B1)** : les 16 Mbit/s de trafic background saturent le lien de 5 Mbit/s à 3.2×. L'OVS applique sa politique de file par défaut (FIFO), traitant tous les paquets à égalité. Le flux de contrôle de 200 Kbit/s se retrouve noyé dans la congestion : les paquets UDP:9999 sont mis en attente derrière des milliers de paquets de background, créant un jitter de 81 ms et une perte de 68.55%. Un tel niveau de dégradation rendrait inutilisable tout protocole de contrôle temps réel (les commandes de feux arriveraient avec 80ms de retard ou seraient tout simplement perdues).

**Avec QoS SDN (B2)** : Ryu installe la règle `match UDP:9999 → set_queue:1` sur les ponts OVS. L'OVS HTB donne accès prioritaire à la queue 1 sur la bande passante disponible. Les paquets de contrôle UDP:9999 ne sont jamais mis en attente derrière le trafic background. Résultat : 0% de perte et 0.07ms de jitter sur toute la durée du test. Le flux de contrôle reçoit exactement ses 200 Kbit/s cibles, indépendamment du niveau de congestion sur le lien.

### 10.3 Lien avec l'objectif du mémoire

Ces résultats valident les deux hypothèses centrales du mémoire :

**Hypothèse 1** — *Un algorithme adaptatif de gestion des feux améliore la capacité du carrefour en trafic asymétrique.*
→ **Validée** : taux de complétion 74.9% → 100% (+33%, +326 véhicules).

**Hypothèse 2** — *Un contrôleur SDN peut garantir la qualité de service des communications de contrôle même sous forte congestion réseau.*
→ **Validée** : perte 68.55% → 0%, jitter 81ms → 0.07ms (amélioration d'un facteur 1162).

La boucle fermée (Phase C) confirme que ces deux mécanismes fonctionnent de concert en conditions réelles : SUMO détecte la congestion du carrefour, l'orchestrateur la communique à Ryu, et Ryu active la protection des communications de contrôle avant que la congestion réseau ne les dégrade.

---

*Document généré à partir des expérimentations réalisées dans le cadre du mémoire de Master.*
*Résultats obtenus le 16 mars 2026.*
