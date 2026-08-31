# Schemas de Tests Complets

Ce document decrit **tous les tests a executer** pour le memoire, etape par etape. Chaque schema est independant. Les executer dans l'ordre : A d'abord, puis B, puis C.

**Structure du projet** :
- `pyfilesTrue/` : code source Python (Ryu, orchestrateur, topologie)
- `scripts/` : scripts shell de lancement
- `tools/` : outils d'analyse (SUMO, iperf, merge)
- `sumo_one_junction/` : config SUMO
- `result/` : resultats

---
---

# PHASE A : Tests Trafic (SUMO)

**But** : Montrer que l'orchestrateur adaptatif evite la saturation par rapport aux feux fixes, sur un scenario de trafic asymetrique (1300 vehicules).

**Duree estimee** : 15 minutes au total.

**Terminaux necessaires** : 1 seul.

---

## Test A1 : Baseline (feux fixes)

Les feux restent a 31s NS / 31s EW. Ils ne s'adaptent pas a la demande.

```bash
cd /home/jmazeph/experiments
bash scripts/LANCER_BASELINE_ASYMMETRIC.sh
```

**Attendre** la fin (quelques minutes). Verifier :

```bash
grep -c '<tripinfo ' results/tripinfo_baseline_asym.xml
```

Resultat attendu : **< 1300** vehicules (le baseline ne les fait pas tous passer).

Fichiers generes :
- `results/tripinfo_baseline_asym.xml`
- `results/sumo_baseline_asym.json`

---

## Test A2 : Adaptive (orchestrateur)

L'orchestrateur detecte quelle direction est chargee et donne plus de vert a cette direction.

```bash
bash scripts/LANCER_ADAPTIVE_ASYMMETRIC.sh
```

**Attendre** la fin. Verifier les changements de phase dans les logs :

```bash
grep -c "Switch -> NS_GREEN" results/orchestrator_asym.log
grep -c "Switch -> EW_GREEN" results/orchestrator_asym.log
```

Resultat attendu : les deux compteurs sont > 0 (alternance), et **1300** vehicules termines.

Fichiers generes :
- `results/tripinfo_adaptive_asym.xml`
- `results/sumo_adaptive_asym.json`
- `results/orchestrator_asym.log`

---

## Test A3 : Comparaison

```bash
bash scripts/COMPARER_ASYMMETRIC.sh
```

**Metrique cle : le taux de completion.**

| Metrique | Baseline | Adaptive | Attendu |
|----------|----------|----------|---------|
| Vehicules termines | ~974/1300 (75%) | **1300/1300 (100%)** | Gain majeur |
| Vehicules sauves | -- | ~326 | +33% |
| Temps d'attente moyen | ~82s | ~82s | Similaire* |
| Throughput | ~974 veh/h | ~977 veh/h | Similaire* |

*Les moyennes par vehicule sont similaires a cause du **biais du survivant** : le baseline ne mesure que les 974 vehicules qui ont reussi a passer. Les 326 bloques sont invisibles dans les moyennes.

**Conclusion Phase A** : L'orchestrateur adaptatif fait passer **100% des vehicules** la ou le baseline en bloque 25%. C'est le chiffre cle pour la these.

---
---

# PHASE B : Tests Reseau (Mininet-WiFi + Ryu)

**But** : Montrer que la QoS SDN protege le flux de controle (UDP:9999) quand le reseau est sature.

**Duree estimee** : 20 minutes au total (2 x 5 min de setup + 2 x 2 min de test).

**Note importante** : dans le CLI Mininet, les redirections `>` ne fonctionnent pas directement. Utiliser `bash -c "commande > fichier"` a la place.

---
---

## SCHEMA B1 : Test SANS QoS (Baseline Reseau)

**But** : Mesurer le jitter et les pertes quand il n'y a **aucune priorite**. Tout le trafic est traite pareil.

**Terminaux necessaires** : 2 (Ryu + Mininet).

---

### Etape B1.1 -- Lancer Ryu (Terminal 1)

Ryu doit tourner pour que les AP OVS fonctionnent. Personne ne lui envoie de metriques, donc la QoS reste desactivee.

a
```bash
cd /home/jmazeph/experiments

activer l'environnement
source ~/ryu-env39/bin/activate

ryu-manager pyfilesTrue/ryu_qos_rest.py
```

**Attendre** de voir :
```
[Ryu] QoS REST app is up on /metrics (enable>=8.0, disable<=3.0; udp=9999)
```

Ne pas fermer ce terminal.

---

### Etape B1.2 -- Lancer la topologie Mininet-WiFi (Terminal 2)

Lancer **SANS** l'option `--configure-qos`. Le lien edge (ap1 <-> edge) est limite a 5 Mbit/s pour creer la congestion.

**Pourquoi `--bw-edge` et non `--bw-backhaul` ?** Toutes les voitures sont proches de AP1 et ne passent jamais par le backhaul (ap1 <-> ap2). Le trafic transite par ap1-eth3 vers edge. Limiter le backhaul ne cree aucune congestion.

```bash
cd /home/jmazeph/experiments
sudo python3 pyfilesTrue/traffic_topology_corridor.py \
  --bw-edge 5 --delay-edge 5ms
```

**Attendre** le prompt `mininet-wifi>`.

---

### Etape B1.3 -- Verifier la connectivite (dans Mininet)

```
pingall
```

Toutes les stations doivent atteindre edge (10.0.0.254). Si pertes, attendre 10s et refaire.

---

### Etape B1.4 -- Lancer les serveurs iperf (dans Mininet)

```
edge bash -c "iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_noqos.log 2>&1" &
edge bash -c "iperf -s -u -p 5001 > /tmp/bg_server.log 2>&1" &
```

---

### Etape B1.5 -- Lancer le trafic de fond (dans Mininet)

car2 et car3 envoient 8 Mbit/s chacun = **16 Mbit/s** sur un lien edge de **5 Mbit/s** = **forte congestion**.

```
car2 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
car3 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
```

---

### Etape B1.6 -- Lancer le flux de controle (dans Mininet)

```
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1
```

(Pas de `&` ici : on attend qu'il finisse pour voir le resultat client.)

---

### Etape B1.7 -- Attendre 120 secondes

Ne rien toucher. Verifier que la QoS est bien **desactivee** :

```bash
curl http://localhost:8080/health
```

Resultat attendu : `{"status":"ok","priority_enabled":false}`

---

### Etape B1.8 -- Recuperer les resultats

Dans Mininet :

```
sh cp /tmp/ctrl_server_noqos.log /home/jmazeph/experiments/results/ctrl_server_noqos.log
```

---

### Etape B1.9 -- Quitter proprement

Dans Mininet : `exit`

Dans Terminal 1 (Ryu) : `Ctrl+C`

---

### Etape B1.10 -- Analyser

```bash
cd /home/jmazeph/experiments
python3 tools/analyze_iperf.py \
  --log results/ctrl_server_noqos.log \
  --out results/ctrl_noqos.json \
  --csv results/ctrl_noqos.csv
```

**Garder ce fichier.** Il sera compare au test AVEC QoS.

---
---

## SCHEMA B2 : Test AVEC QoS (Priorite SDN Activee)

**But** : Mesurer les memes metriques, mais avec les files de priorite OVS activees. Les paquets UDP:9999 passent dans la queue prioritaire.

**Terminaux necessaires** : 2 (Ryu + Mininet). On utilise `scripts/force_qos_on.sh` pour activer la QoS sans avoir besoin de SUMO.

---

### Etape B2.1 -- Lancer Ryu (Terminal 1)

```bash
cd /home/jmazeph/experiments

activer l'environnement
source ~/ryu-env39/bin/activate

ryu-manager pyfilesTrue/ryu_qos_rest.py
```

**Attendre** le message de demarrage. Ne pas fermer.

---

### Etape B2.2 -- Lancer la topologie AVEC QoS (Terminal 2)

Cette fois, ajouter **`--configure-qos`** pour creer les queues HTB. Meme lien edge a 5 Mbit/s.

```bash
cd /home/jmazeph/experiments
sudo python3 pyfilesTrue/traffic_topology_corridor.py \
  --bw-edge 5 --delay-edge 5ms \
  --configure-qos
```

**Attendre** le prompt `mininet-wifi>`.

Les logs doivent montrer `Attaching OVS QoS (HTB) queues on wired ports`.

---

### Etape B2.3 -- Verifier la connectivite (dans Mininet)

```
pingall
```

---

### Etape B2.4 -- Verifier les queues OVS (dans Mininet)

```
sh sudo ovs-vsctl list qos
```

Doit afficher des entrees QoS de type `linux-htb`. Si vide, les queues ne sont pas en place.

---

### Etape B2.5 -- Activer la QoS manuellement

Depuis un autre terminal (ou dans Mininet avec `sh`) :

bash scripts/force_qos_on.sh
```

Ou manuellement :

```bash
curl -X POST http://localhost:8080/metrics \
  -H "Content-Type: application/json" \
  -d '{"busy": 20, "ns_q": 10, "ew_q": 10}'
```

**Verifier** que la QoS est activee :

```bash
curl http://localhost:8080/health
```

Resultat **obligatoire** : `{"status":"ok","priority_enabled":true}`

**Verifier** les regles OpenFlow :

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue
```

Doit afficher des lignes avec `udp,tp_dst=9999 actions=set_queue:1,NORMAL`.

**Ne pas continuer si `priority_enabled` est `false`.**

---

### Etape B2.6 -- Lancer les serveurs iperf (dans Mininet)

```
edge bash -c "iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_qos.log 2>&1" &
edge bash -c "iperf -s -u -p 5001 > /tmp/bg_server_qos.log 2>&1" &
```

---

### Etape B2.7 -- Lancer le trafic de fond (dans Mininet)

```
car2 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
car3 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
```

---

### Etape B2.8 -- Lancer le flux de controle (dans Mininet)

```
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1
```

---

### Etape B2.9 -- Attendre 120 secondes

Pendant l'attente, verifier que la QoS est toujours active :

```bash
curl http://localhost:8080/health
```

Doit rester `"priority_enabled":true`.

---

### Etape B2.10 -- Recuperer les resultats

Dans Mininet :

```
sh cp /tmp/ctrl_server_qos.log /home/jmazeph/experiments/results/ctrl_server_qos.log
```

---

### Etape B2.11 -- Quitter proprement

Dans Mininet : `exit`

Dans Terminal 1 (Ryu) : `Ctrl+C`

---

### Etape B2.12 -- Analyser

```bash
cd /home/jmazeph/experiments
python3 tools/analyze_iperf.py \
  --log results/ctrl_server_qos.log \
  --out results/ctrl_qos.json \
  --csv results/ctrl_qos.csv
```

---
---

## Comparaison B1 vs B2

**Resultats attendus** (avec congestion reelle) :

| Metrique | Sans QoS (B1) | Avec QoS (B2) | Attendu |
|----------|---------------|---------------|---------|
| Jitter moyen | 5-50 ms | < 1 ms | Reduction forte |
| Perte de paquets | 10-40% | < 5% | Reduction forte |
| Bande passante ctrl | Instable | Stable ~0.2 Mb/s | Stabilisation |
| `priority_enabled` | `false` | `true` | -- |
| Regles `set_queue` | Aucune | `set_queue:1` sur UDP:9999 | -- |

---

## Differences cles entre B1 et B2

| Element | B1 (Sans QoS) | B2 (Avec QoS) |
|---------|---------------|---------------|
| Lien edge | `--bw-edge 5 --delay-edge 5ms` | idem |
| Option topologie | Pas de `--configure-qos` | `--configure-qos` |
| Activation QoS | Non | `scripts/force_qos_on.sh` ou `curl` |
| Queues OVS HTB | Non creees | Creees (queue 0 + queue 1) |
| Ryu installe des regles | Non | Oui (`set_queue:1` pour UDP:9999) |
| Fichier de sortie | `ctrl_server_noqos.log` | `ctrl_server_qos.log` |

---

## Rappel important

Le jitter et les pertes sont **uniquement** dans les logs **cote serveur** (edge). Les logs client (car1) ne montrent que la bande passante. Le script `analyze_iperf.py` detecte automatiquement le type de log.

---
---

# PHASE C : Test Integre (Boucle Fermee)

**But** : Demontrer que tout fonctionne ensemble : SUMO detecte la congestion, l'orchestrateur previent Ryu, et Ryu active la QoS en temps reel.

**Duree estimee** : 25 minutes (SUMO tourne en temps reel).

**Terminaux necessaires** : 3.

---

### Etape C.1 -- Lancer Ryu (Terminal 1)

```bash
cd /home/jmazeph/experiments
ryu-manager pyfilesTrue/ryu_qos_rest.py
```

Attendre le message de demarrage.

---

### Etape C.2 -- Lancer la topologie AVEC QoS (Terminal 2)

```bash
cd /home/jmazeph/experiments
sudo python3 pyfilesTrue/traffic_topology_corridor.py \
  --bw-edge 5 --delay-edge 5ms \
  --configure-qos
```

Attendre `mininet-wifi>`. Faire un `pingall` pour verifier.

---

### Etape C.3 -- Lancer SUMO + orchestrateur en temps reel (Terminal 3)

```bash
cd /home/jmazeph/experiments/sumo_one_junction
sumo -c one_junction_asymmetric.sumocfg \
  --remote-port 8813 \
  --end 3600 \
  --seed 42 \
  --time-to-teleport -1 &

sleep 3

cd /home/jmazeph/experiments
sudo python3 pyfilesTrue/tls_orchestrator_CORRECTED.py \
  --sumo-port 8813 \
  --tls-id J1 \
  --ns-phase-idx 0 \
  --ew-phase-idx 2 \
  --min-green 10 \
  --max-green 45 \
  --hysteresis 0.15 \
  --post-url http://localhost:8080/metrics \
  --realtime
```

L'option **`--realtime`** est essentielle : elle synchronise SUMO avec le temps reel. Sans elle, SUMO finit en 2 minutes et la QoS est desactivee avant qu'on puisse tester.

**Attendre ~30-40 secondes** que les files SUMO se remplissent.

---

### Etape C.4 -- Verifier que Ryu a active la QoS

```bash
curl http://localhost:8080/health
```

Resultat **obligatoire** : `"priority_enabled": true`

Si c'est `false`, attendre encore 30s (les files doivent depasser busy >= 8).

Verifier aussi les regles OVS :

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue
```

---

### Etape C.5 -- Lancer les tests iperf (dans Mininet, Terminal 2)

```
edge bash -c "iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_integre.log 2>&1" &
edge bash -c "iperf -s -u -p 5001 > /tmp/bg_server_integre.log 2>&1" &
car2 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
car3 bash -c "iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 > /dev/null 2>&1" &
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1
```

---

### Etape C.6 -- Attendre 120 secondes

Pendant ce temps, observer dans Terminal 3 (orchestrateur) que les switchs de phase continuent. Observer dans Terminal 1 (Ryu) que les messages `priority_enabled` restent actifs.

---

### Etape C.7 -- Recuperer et analyser

```
sh cp /tmp/ctrl_server_integre.log /home/jmazeph/experiments/results/ctrl_server_integre.log
```

```bash
cd /home/jmazeph/experiments
python3 tools/analyze_iperf.py \
  --log results/ctrl_server_integre.log \
  --out results/ctrl_integre.json \
  --csv results/ctrl_integre.csv
```

---

### Etape C.8 -- Quitter proprement

1. Dans Mininet : `exit`
2. Dans Terminal 3 : `Ctrl+C` (arrete l'orchestrateur, SUMO s'arrete aussi)
3. Dans Terminal 1 : `Ctrl+C` (arrete Ryu)

---
---

# PHASE D : Rapport Final

Une fois les phases A, B et C terminees :

```bash
cd /home/jmazeph/experiments
python3 tools/merge_report.py \
  --sumo-baseline results/sumo_baseline_asym.json \
  --sumo-adaptive results/sumo_adaptive_asym.json \
  --ctrl-noqos results/ctrl_noqos.json \
  --ctrl-qos results/ctrl_qos.json \
  --out results/report.md
```

Ce rapport contient les deux tableaux comparatifs : mobilite (Phase A) et reseau (Phase B).

---

## Checklist finale

| Verification | Fait ? |
|---|---|
| Phase A : baseline asymetrique executee (attendre < 1300 veh) | |
| Phase A : adaptive asymetrique executee (attendre 1300 veh, alternance) | |
| Phase A : comparaison montre gain de completion (+33%) | |
| Phase B1 : test sans QoS avec trafic de fond (16M sur 5M edge) | |
| Phase B2 : test avec QoS, `priority_enabled=true` verifie | |
| Phase B : comparaison montre reduction du jitter et des pertes | |
| Phase C : test integre en temps reel (boucle fermee) | |
| Phase D : rapport fusionne genere | |
