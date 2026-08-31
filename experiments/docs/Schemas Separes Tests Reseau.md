# Schémas Séparés : Test SANS QoS puis Test AVEC QoS

Ce document présente **deux schémas complètement séparés**. D'abord le test SANS QoS (baseline réseau), ensuite le test AVEC QoS. Chaque schéma a ses propres terminaux, ses propres commandes, et ses propres fichiers de sortie. Ne pas les mélanger.

***

***

# SCHÉMA 1 : TEST SANS QoS (Baseline Réseau)

**But** : Mesurer le jitter et les pertes du flux de contrôle (UDP:9999) quand il n'y a **aucune priorité**. Tout le trafic est traité pareil.

***

## Terminaux nécessaires

Il faut ouvrir **2 terminaux** sur la machine Ubuntu.

***

## Étape 1.1 — Lancer Ryu (Terminal 1)

Ryu est le contrôleur SDN. Il doit tourner pour que les AP OVS fonctionnent. Mais pour ce test, **personne ne lui envoie de métriques**, donc la QoS reste désactivée.[^1]

```bash
cd /home/jmazeph/experiments
ryu-manager ryu_qos_rest.py
```

**Attendre** de voir cette ligne dans le terminal :

```
[Ryu] QoS REST app is up on /metrics (enable>=8.0, disable<=3.0; udp=9999)
```

**Ne pas fermer ce terminal.** Le laisser tourner.

***

## Étape 1.2 — Lancer la topologie Mininet-WiFi (Terminal 2)

Lancer la topologie **SANS l'option `--configure-qos`** et avec un backhaul de 10 Mbit/s pour créer de la congestion.[^2]

```bash
cd /home/jmazeph/experiments
sudo python3 traffic_topology_corridor.py --bw-backhaul 10 --delay-backhaul 10ms --loss-backhaul 0.2
```

**Attendre** de voir le prompt Mininet :

```
mininet-wifi>
```

***

## Étape 1.3 — Vérifier la connectivité (dans Mininet)

Taper dans le prompt `mininet-wifi>` :

```
pingall
```

Toutes les stations (car1, car2, car3) doivent pouvoir atteindre edge (10.0.0.254). S'il y a des pertes, attendre 10 secondes et refaire `pingall`.

***

## Étape 1.4 — Lancer le serveur iperf sur edge (dans Mininet)

Le serveur iperf doit tourner sur **edge** (pas sur les cars). C'est le serveur qui capture le jitter et les pertes.[^3]

```
edge iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_noqos.log &
```

Puis lancer aussi un serveur pour le trafic de fond :

```
edge iperf -s -u -p 5001 > /tmp/bg_server.log &
```

***

## Étape 1.5 — Lancer le trafic de fond (dans Mininet)

car2 et car3 envoient du gros trafic pour saturer le lien de 10 Mbit/s :

```
car2 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car3 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
```

Le lien fait 10 Mbit/s, les 2 cars envoient 8+8 = 16 Mbit/s → **congestion**.

***

## Étape 1.6 — Lancer le flux de contrôle (dans Mininet)

car1 envoie le flux de contrôle simulé (port UDP 9999, faible débit) :

```
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1 &
```

***

## Étape 1.7 — Attendre 120 secondes

Laisser tourner pendant **2 minutes**. Ne rien toucher.

Optionnel : vérifier que Ryu n'a **PAS** activé la QoS (depuis un autre terminal ou après le test) :

```bash
curl http://localhost:8080/health
```

Résultat attendu : `{"status":"ok","priority_enabled":false}`[^1]

***

## Étape 1.8 — Récupérer les résultats

Après 120 secondes, dans le prompt `mininet-wifi>` :

```
edge cat /tmp/ctrl_server_noqos.log
```

Puis copier ce fichier vers le dossier résultats :

```
sh cp /tmp/ctrl_server_noqos.log /home/jmazeph/experiments/results/ctrl_server_noqos.log
```

***

## Étape 1.9 — Quitter proprement

```
exit
```

Cela ferme Mininet. Puis dans le **Terminal 1**, faire `Ctrl+C` pour arrêter Ryu.

***

## Étape 1.10 — Analyser les résultats

```bash
cd /home/jmazeph/experiments
python3 analyze_iperf.py \
  --log results/ctrl_server_noqos.log \
  --out results/ctrl_noqos.json \
  --csv results/ctrl_noqos.csv
```

Le fichier `ctrl_noqos.json` contient : jitter moyen, perte moyenne, bandwidth. **Garder ce fichier précieusement**, il sera comparé au test AVEC QoS.[^3]

***

***

# SCHÉMA 2 : TEST AVEC QoS (Priorité SDN Activée)

**But** : Mesurer les mêmes métriques, mais cette fois avec les files de priorité OVS activées et l'orchestrateur qui envoie les métriques à Ryu. Les paquets UDP:9999 passent dans la queue prioritaire.

***

## Terminaux nécessaires

Il faut ouvrir **3 terminaux** sur la machine Ubuntu (un de plus que le schéma 1, pour l'orchestrateur SUMO).

***

## Étape 2.1 — Lancer Ryu (Terminal 1)

Exactement pareil que le schéma 1 :

```bash
cd /home/jmazeph/experiments
ryu-manager ryu_qos_rest.py
```

**Attendre** de voir :

```
[Ryu] QoS REST app is up on /metrics (enable>=8.0, disable<=3.0; udp=9999)
```

**Ne pas fermer ce terminal.**

***

## Étape 2.2 — Lancer la topologie AVEC QoS (Terminal 2)

Cette fois, ajouter l'option **`--configure-qos`** qui crée les files HTB sur les ports OVS (queue 0 = best-effort, queue 1 = priorité) :[^2]

```bash
cd /home/jmazeph/experiments
sudo python3 traffic_topology_corridor.py --bw-backhaul 10 --delay-backhaul 10ms --loss-backhaul 0.2 --configure-qos
```

**Attendre** le prompt :

```
mininet-wifi>
```

Les lignes de log doivent montrer `Attaching OVS QoS (HTB) queues on wired ports` — cela confirme que les queues sont en place.

***

## Étape 2.3 — Vérifier la connectivité (dans Mininet)

```
pingall
```

S'assurer que tout communique. Si pertes, attendre et refaire.

***

## Étape 2.4 — Vérifier les queues OVS (dans Mininet)

```
sh sudo ovs-vsctl list qos
```

Cela doit afficher des entrées QoS de type `linux-htb`. S'il n'y a rien, les queues ne sont pas en place et la QoS ne marchera pas.

***

## Étape 2.5 — Lancer SUMO + orchestrateur (Terminal 3)

L'orchestrateur SUMO doit tourner pour envoyer les métriques `busy` à Ryu. C'est la **différence clé** avec le schéma 1.[^4]

D'abord lancer SUMO :

```bash
cd /home/jmazeph/experiments/sumo_one_junction
sumo -c one_junction.sumocfg \
  --remote-port 8813 \
  --end 3600 \
  --seed 42 \
  --time-to-teleport -1 &
```

Attendre 3 secondes, puis lancer l'orchestrateur avec `--post-url` qui pointe vers Ryu :

```bash
cd /home/jmazeph/experiments
sudo python3 tls_orchestrator_CORRECTED.py \
  --sumo-port 8813 \
  --tls-id J1 \
  --ns-phase-idx 0 \
  --ew-phase-idx 2 \
  --min-green 10 \
  --max-green 45 \
  --hysteresis 0.15 \
  --post-url http://localhost:8080/metrics
```

Dans le **Terminal 1** (Ryu), des messages vont apparaître quand le `busy` dépasse 8 :

```
[Ryu] Installed priority rule on dpid=...
```

Cela signifie que Ryu a installé la règle `set_queue:1` pour UDP:9999. **C'est la QoS en action.**[^1]

***

## Étape 2.6 — Lancer le serveur iperf sur edge (dans Mininet, Terminal 2)

```
edge iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_qos.log &
edge iperf -s -u -p 5001 > /tmp/bg_server_qos.log &
```

***

## Étape 2.7 — Lancer le trafic de fond (dans Mininet)

Mêmes commandes que le schéma 1 :

```
car2 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car3 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
```

***

## Étape 2.8 — Lancer le flux de contrôle (dans Mininet)

```
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1 &
```

***

## Étape 2.9 — Attendre 120 secondes

Pendant l'attente, vérifier que la QoS est bien active :

```bash
curl http://localhost:8080/health
```

Résultat attendu : `{"status":"ok","priority_enabled":true}`[^1]

Et vérifier les règles OpenFlow installées (depuis un autre terminal) :

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue
```

Cela doit afficher une ligne contenant `udp,tp_dst=9999 actions=set_queue:1,NORMAL`.[^1]

***

## Étape 2.10 — Récupérer les résultats

Dans Mininet :

```
edge cat /tmp/ctrl_server_qos.log
sh cp /tmp/ctrl_server_qos.log /home/jmazeph/experiments/results/ctrl_server_qos.log
```

***

## Étape 2.11 — Quitter proprement

Dans Mininet :

```
exit
```

Dans le **Terminal 3** (orchestrateur) : attendre qu'il finisse ou `Ctrl+C`.

Dans le **Terminal 1** (Ryu) : `Ctrl+C`.

***

## Étape 2.12 — Analyser les résultats

```bash
cd /home/jmazeph/experiments
python3 analyze_iperf.py \
  --log results/ctrl_server_qos.log \
  --out results/ctrl_qos.json \
  --csv results/ctrl_qos.csv
```

***

***

# COMPARAISON FINALE

Une fois les deux schémas terminés, les 2 fichiers JSON sont prêts.

## Générer le rapport fusionné

```bash
cd /home/jmazeph/experiments
python3 merge_report.py \
  --sumo-baseline results/sumo_baseline.json \
  --sumo-adaptive results/sumo_adaptive.json \
  --ctrl-noqos results/ctrl_noqos.json \
  --ctrl-qos results/ctrl_qos.json \
  --out results/report.md
```

Ce rapport contient un tableau comparatif complet : mobilité (Phase A déjà faite) + réseau (Phase B).[^5]

## Ce qu'il faut observer

| Métrique | Schéma 1 (SANS QoS) | Schéma 2 (AVEC QoS) |
|----------|---------------------|---------------------|
| Jitter moyen | Élevé (le flux de contrôle est noyé dans la congestion) | Faible (la queue prioritaire le protège) |
| Perte de paquets (%) | Significative (pas de traitement spécial) | Très faible (débit garanti par `min-rate`) |
| Bandwidth du flux de contrôle | Instable (écrasé par le trafic de fond) | Stable ~0.2 Mb/s (isolé dans sa queue) |
| `priority_enabled` dans Ryu | `false` (personne n'envoie de métriques) | `true` (l'orchestrateur poste `busy`) |
| Règles `set_queue` dans OVS | Aucune | `set_queue:1` sur UDP:9999 |

## Différences clés entre les deux schémas

| Élément | Schéma 1 (SANS QoS) | Schéma 2 (AVEC QoS) |
|---------|---------------------|---------------------|
| Option topologie | Pas de `--configure-qos` | `--configure-qos`[^2] |
| Orchestrateur SUMO | **Non lancé** | **Lancé** avec `--post-url`[^4] |
| Terminaux nécessaires | 2 (Ryu + Mininet) | 3 (Ryu + Mininet + Orchestrateur) |
| Queues OVS HTB | Non créées | Créées (queue 0 + queue 1) |
| Ryu installe des règles | Non | Oui, quand `busy ≥ 8`[^1] |
| Fichier de sortie serveur | `ctrl_server_noqos.log` | `ctrl_server_qos.log` |
| Fichier JSON analysé | `ctrl_noqos.json` | `ctrl_qos.json` |

## Rappel important

Le jitter et les pertes de paquets sont uniquement visibles dans les logs **côté serveur** (edge). Les logs client (car1) ne montrent que le bandwidth. Le script `analyze_iperf.py` le détecte automatiquement et affiche un avertissement si un log client est utilisé.[^3]

---

## References

1. [ryu_qos_rest.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/48ad8f09-30cd-4297-ad28-0e2b5ea25593/ryu_qos_rest.py?AWSAccessKeyId=ASIA2F3EMEYETJKQXEVU&Signature=dx47%2FSOY5ofspUuMxg54SzpkBDM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCWHHhbB21tH3jP2l24raE1vLOizmIs2Jyyj7Di4VnzIgIgcxZr6m3fohy0DFyF7Ic%2Fz4rgzeuAabuJ9ZY2FypxQO0q8wQIVBABGgw2OTk3NTMzMDk3MDUiDF%2FBqDOHIoVeczP7aSrQBBz58So1v9KRfwmYV%2FPdySosK4UEYHMTVIHHVBpR1Az49aydIaa3H1BsVrDFo4zhaBKz77PVwA0AkriZKykePDH0gwz7s%2F3IBYh3l2J0swhJpfNcr5%2BRBUIHjJp4AE47FO2crc4m0vgMiDkNuwjDB91dtrvXyYxZaz9MAFS7TEhVPujwqlAR5SFInvXmnlo5EjZrFAoVqKbQ8A2BKjlUOVfIuBZqZJALIDc4CNSt929vW9oYWxdVujcqnGdztZEL%2B4vNHaN2kWg8EQFDi8Fpcy2fCsQNrmSEafT%2FtSRv%2FuhnhQBuNZ7Jn7aL9ayR1JjdrIMoeppel8izoeyjBsB7xen36T%2F%2BctehbMO9ur1q0PK0datudHlTVFhKaTBtbMtD%2F%2FNXzoAMzAF6YplU8DugHWYHSbuBF6DMs5QwTS8Wt8jDN%2Fb4niRwTH1Q7ubzSnwVzfJrqat7D2hC4D0hDJYODqSP2pBtAjn3m4S05C5gBhriIH4R9iDOOTRle4v9OGOLN%2FCn9DFTKg%2BcSv4YN9PdoOLFqMxeI7spU9sDdiOxOW3DAuEbhtzZAe4BUAJ5ldd97wpxtGI3N7dPvJ8yL7b%2BHma9eko1OCogDqE21zUEXjKI62jYmdOxuZWp%2BPGeTXz53S2DP7oNsQTlJc48AQlIG%2Fb2NqgZjLjCA%2BVXxDDEDLQQzUzDZgk17Ti8uWzZGqUVYCsJ%2BHxV88J5UZyGbmT3VUti1x8Ypmla0O6pMhgJOsNkJD6PWLb5GiUMGFKUB3oNwc8IWXl0wwPIxt69Y%2BVySJEwtIeLzQY6mAFkBK4A5wu%2FrBrW1mUjT4gw6r4nA%2F0aIe%2BhzE6500VpR9H%2BP4gcvKKaDqP7uoCicgsSkzncM5NXJenea0iRqO7Ja%2FhZdSvfxyltA4ZbYgNAZLSqcxc838J%2BsDIRr5j091lmGtgCFiISZr%2FI4yjl8YfM4RochnX9usD2mjnAOW99Wk4rQlw9VGVC7MHhlCOCedc%2F2%2BVXVFNn8Q%3D%3D&Expires=1772279053) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ryu QoS REST app (OpenFlow 1.3)

Purpose
-------
...

2. [traffic_topology_corridor.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/fc55248c-20ae-485f-b61a-a165aa39a9ea/traffic_topology_corridor.py?AWSAccessKeyId=ASIA2F3EMEYETJKQXEVU&Signature=AcsVi%2FpMOak7L7pgyFar1iZRIm8%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCWHHhbB21tH3jP2l24raE1vLOizmIs2Jyyj7Di4VnzIgIgcxZr6m3fohy0DFyF7Ic%2Fz4rgzeuAabuJ9ZY2FypxQO0q8wQIVBABGgw2OTk3NTMzMDk3MDUiDF%2FBqDOHIoVeczP7aSrQBBz58So1v9KRfwmYV%2FPdySosK4UEYHMTVIHHVBpR1Az49aydIaa3H1BsVrDFo4zhaBKz77PVwA0AkriZKykePDH0gwz7s%2F3IBYh3l2J0swhJpfNcr5%2BRBUIHjJp4AE47FO2crc4m0vgMiDkNuwjDB91dtrvXyYxZaz9MAFS7TEhVPujwqlAR5SFInvXmnlo5EjZrFAoVqKbQ8A2BKjlUOVfIuBZqZJALIDc4CNSt929vW9oYWxdVujcqnGdztZEL%2B4vNHaN2kWg8EQFDi8Fpcy2fCsQNrmSEafT%2FtSRv%2FuhnhQBuNZ7Jn7aL9ayR1JjdrIMoeppel8izoeyjBsB7xen36T%2F%2BctehbMO9ur1q0PK0datudHlTVFhKaTBtbMtD%2F%2FNXzoAMzAF6YplU8DugHWYHSbuBF6DMs5QwTS8Wt8jDN%2Fb4niRwTH1Q7ubzSnwVzfJrqat7D2hC4D0hDJYODqSP2pBtAjn3m4S05C5gBhriIH4R9iDOOTRle4v9OGOLN%2FCn9DFTKg%2BcSv4YN9PdoOLFqMxeI7spU9sDdiOxOW3DAuEbhtzZAe4BUAJ5ldd97wpxtGI3N7dPvJ8yL7b%2BHma9eko1OCogDqE21zUEXjKI62jYmdOxuZWp%2BPGeTXz53S2DP7oNsQTlJc48AQlIG%2Fb2NqgZjLjCA%2BVXxDDEDLQQzUzDZgk17Ti8uWzZGqUVYCsJ%2BHxV88J5UZyGbmT3VUti1x8Ypmla0O6pMhgJOsNkJD6PWLb5GiUMGFKUB3oNwc8IWXl0wwPIxt69Y%2BVySJEwtIeLzQY6mAFkBK4A5wu%2FrBrW1mUjT4gw6r4nA%2F0aIe%2BhzE6500VpR9H%2BP4gcvKKaDqP7uoCicgsSkzncM5NXJenea0iRqO7Ja%2FhZdSvfxyltA4ZbYgNAZLSqcxc838J%2BsDIRr5j091lmGtgCFiISZr%2FI4yjl8YfM4RochnX9usD2mjnAOW99Wk4rQlw9VGVC7MHhlCOCedc%2F2%2BVXVFNn8Q%3D%3D&Expires=1772279053) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traffic_topology_corridor.py
--------------------...

3. [analyze_iperf.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/6ebf8033-e657-4c62-8cd4-c338432a0d3b/analyze_iperf.py?AWSAccessKeyId=ASIA2F3EMEYETJKQXEVU&Signature=rhvfNZJfTcAqyfxHzmnLpKuzTaM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCWHHhbB21tH3jP2l24raE1vLOizmIs2Jyyj7Di4VnzIgIgcxZr6m3fohy0DFyF7Ic%2Fz4rgzeuAabuJ9ZY2FypxQO0q8wQIVBABGgw2OTk3NTMzMDk3MDUiDF%2FBqDOHIoVeczP7aSrQBBz58So1v9KRfwmYV%2FPdySosK4UEYHMTVIHHVBpR1Az49aydIaa3H1BsVrDFo4zhaBKz77PVwA0AkriZKykePDH0gwz7s%2F3IBYh3l2J0swhJpfNcr5%2BRBUIHjJp4AE47FO2crc4m0vgMiDkNuwjDB91dtrvXyYxZaz9MAFS7TEhVPujwqlAR5SFInvXmnlo5EjZrFAoVqKbQ8A2BKjlUOVfIuBZqZJALIDc4CNSt929vW9oYWxdVujcqnGdztZEL%2B4vNHaN2kWg8EQFDi8Fpcy2fCsQNrmSEafT%2FtSRv%2FuhnhQBuNZ7Jn7aL9ayR1JjdrIMoeppel8izoeyjBsB7xen36T%2F%2BctehbMO9ur1q0PK0datudHlTVFhKaTBtbMtD%2F%2FNXzoAMzAF6YplU8DugHWYHSbuBF6DMs5QwTS8Wt8jDN%2Fb4niRwTH1Q7ubzSnwVzfJrqat7D2hC4D0hDJYODqSP2pBtAjn3m4S05C5gBhriIH4R9iDOOTRle4v9OGOLN%2FCn9DFTKg%2BcSv4YN9PdoOLFqMxeI7spU9sDdiOxOW3DAuEbhtzZAe4BUAJ5ldd97wpxtGI3N7dPvJ8yL7b%2BHma9eko1OCogDqE21zUEXjKI62jYmdOxuZWp%2BPGeTXz53S2DP7oNsQTlJc48AQlIG%2Fb2NqgZjLjCA%2BVXxDDEDLQQzUzDZgk17Ti8uWzZGqUVYCsJ%2BHxV88J5UZyGbmT3VUti1x8Ypmla0O6pMhgJOsNkJD6PWLb5GiUMGFKUB3oNwc8IWXl0wwPIxt69Y%2BVySJEwtIeLzQY6mAFkBK4A5wu%2FrBrW1mUjT4gw6r4nA%2F0aIe%2BhzE6500VpR9H%2BP4gcvKKaDqP7uoCicgsSkzncM5NXJenea0iRqO7Ja%2FhZdSvfxyltA4ZbYgNAZLSqcxc838J%2BsDIRr5j091lmGtgCFiISZr%2FI4yjl8YfM4RochnX9usD2mjnAOW99Wk4rQlw9VGVC7MHhlCOCedc%2F2%2BVXVFNn8Q%3D%3D&Expires=1772279053) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze iperf2 UDP logs (client or server).

Outp...

4. [tls_orchestrator_CORRECTED.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/b0101a47-b348-490b-99dd-30fbfa776de3/tls_orchestrator_CORRECTED.py?AWSAccessKeyId=ASIA2F3EMEYETJKQXEVU&Signature=Yu9OJR%2FvUM2IgiZS6naAdBTfXGQ%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCWHHhbB21tH3jP2l24raE1vLOizmIs2Jyyj7Di4VnzIgIgcxZr6m3fohy0DFyF7Ic%2Fz4rgzeuAabuJ9ZY2FypxQO0q8wQIVBABGgw2OTk3NTMzMDk3MDUiDF%2FBqDOHIoVeczP7aSrQBBz58So1v9KRfwmYV%2FPdySosK4UEYHMTVIHHVBpR1Az49aydIaa3H1BsVrDFo4zhaBKz77PVwA0AkriZKykePDH0gwz7s%2F3IBYh3l2J0swhJpfNcr5%2BRBUIHjJp4AE47FO2crc4m0vgMiDkNuwjDB91dtrvXyYxZaz9MAFS7TEhVPujwqlAR5SFInvXmnlo5EjZrFAoVqKbQ8A2BKjlUOVfIuBZqZJALIDc4CNSt929vW9oYWxdVujcqnGdztZEL%2B4vNHaN2kWg8EQFDi8Fpcy2fCsQNrmSEafT%2FtSRv%2FuhnhQBuNZ7Jn7aL9ayR1JjdrIMoeppel8izoeyjBsB7xen36T%2F%2BctehbMO9ur1q0PK0datudHlTVFhKaTBtbMtD%2F%2FNXzoAMzAF6YplU8DugHWYHSbuBF6DMs5QwTS8Wt8jDN%2Fb4niRwTH1Q7ubzSnwVzfJrqat7D2hC4D0hDJYODqSP2pBtAjn3m4S05C5gBhriIH4R9iDOOTRle4v9OGOLN%2FCn9DFTKg%2BcSv4YN9PdoOLFqMxeI7spU9sDdiOxOW3DAuEbhtzZAe4BUAJ5ldd97wpxtGI3N7dPvJ8yL7b%2BHma9eko1OCogDqE21zUEXjKI62jYmdOxuZWp%2BPGeTXz53S2DP7oNsQTlJc48AQlIG%2Fb2NqgZjLjCA%2BVXxDDEDLQQzUzDZgk17Ti8uWzZGqUVYCsJ%2BHxV88J5UZyGbmT3VUti1x8Ypmla0O6pMhgJOsNkJD6PWLb5GiUMGFKUB3oNwc8IWXl0wwPIxt69Y%2BVySJEwtIeLzQY6mAFkBK4A5wu%2FrBrW1mUjT4gw6r4nA%2F0aIe%2BhzE6500VpR9H%2BP4gcvKKaDqP7uoCicgsSkzncM5NXJenea0iRqO7Ja%2FhZdSvfxyltA4ZbYgNAZLSqcxc838J%2BsDIRr5j091lmGtgCFiISZr%2FI4yjl8YfM4RochnX9usD2mjnAOW99Wk4rQlw9VGVC7MHhlCOCedc%2F2%2BVXVFNn8Q%3D%3D&Expires=1772279053) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive TLS Orchestrator - VERSION CORRIGÉE

BUG...

5. [merge_report.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/819b0bf8-d592-45d8-9c4c-7e83ecd887ff/merge_report.py?AWSAccessKeyId=ASIA2F3EMEYETJKQXEVU&Signature=xOEwOdOXu9Ec%2Flr8Tek8H5mZtVM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIv%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJHMEUCIQCWHHhbB21tH3jP2l24raE1vLOizmIs2Jyyj7Di4VnzIgIgcxZr6m3fohy0DFyF7Ic%2Fz4rgzeuAabuJ9ZY2FypxQO0q8wQIVBABGgw2OTk3NTMzMDk3MDUiDF%2FBqDOHIoVeczP7aSrQBBz58So1v9KRfwmYV%2FPdySosK4UEYHMTVIHHVBpR1Az49aydIaa3H1BsVrDFo4zhaBKz77PVwA0AkriZKykePDH0gwz7s%2F3IBYh3l2J0swhJpfNcr5%2BRBUIHjJp4AE47FO2crc4m0vgMiDkNuwjDB91dtrvXyYxZaz9MAFS7TEhVPujwqlAR5SFInvXmnlo5EjZrFAoVqKbQ8A2BKjlUOVfIuBZqZJALIDc4CNSt929vW9oYWxdVujcqnGdztZEL%2B4vNHaN2kWg8EQFDi8Fpcy2fCsQNrmSEafT%2FtSRv%2FuhnhQBuNZ7Jn7aL9ayR1JjdrIMoeppel8izoeyjBsB7xen36T%2F%2BctehbMO9ur1q0PK0datudHlTVFhKaTBtbMtD%2F%2FNXzoAMzAF6YplU8DugHWYHSbuBF6DMs5QwTS8Wt8jDN%2Fb4niRwTH1Q7ubzSnwVzfJrqat7D2hC4D0hDJYODqSP2pBtAjn3m4S05C5gBhriIH4R9iDOOTRle4v9OGOLN%2FCn9DFTKg%2BcSv4YN9PdoOLFqMxeI7spU9sDdiOxOW3DAuEbhtzZAe4BUAJ5ldd97wpxtGI3N7dPvJ8yL7b%2BHma9eko1OCogDqE21zUEXjKI62jYmdOxuZWp%2BPGeTXz53S2DP7oNsQTlJc48AQlIG%2Fb2NqgZjLjCA%2BVXxDDEDLQQzUzDZgk17Ti8uWzZGqUVYCsJ%2BHxV88J5UZyGbmT3VUti1x8Ypmla0O6pMhgJOsNkJD6PWLb5GiUMGFKUB3oNwc8IWXl0wwPIxt69Y%2BVySJEwtIeLzQY6mAFkBK4A5wu%2FrBrW1mUjT4gw6r4nA%2F0aIe%2BhzE6500VpR9H%2BP4gcvKKaDqP7uoCicgsSkzncM5NXJenea0iRqO7Ja%2FhZdSvfxyltA4ZbYgNAZLSqcxc838J%2BsDIRr5j091lmGtgCFiISZr%2FI4yjl8YfM4RochnX9usD2mjnAOW99Wk4rQlw9VGVC7MHhlCOCedc%2F2%2BVXVFNn8Q%3D%3D&Expires=1772279053) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge mobility (SUMO) + network (iperf) JSONs int...

