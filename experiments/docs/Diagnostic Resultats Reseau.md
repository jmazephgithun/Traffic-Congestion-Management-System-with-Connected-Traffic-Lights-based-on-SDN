# Diagnostic Complet des Résultats Réseau — Phase B

## Verdict : Les Tests Réseau N'Ont PAS Fonctionné Correctement

L'analyse croisée des 6 fichiers fournis (`ctrl_noqos.json`, `ctrl_qos.json`, les CSV et les logs iperf) révèle **3 problèmes critiques** qui rendent les résultats actuels inexploitables pour une comparaison SANS QoS / AVEC QoS. Les tests doivent être refaits.

***

## Problème 1 : Résultats Quasi-Identiques (Pas de Congestion)

Les données JSON montrent des métriques presque indifférenciables entre les deux scénarios :[^1][^2]

| Métrique | SANS QoS | AVEC QoS | Attendu |
|----------|----------|----------|---------|
| Jitter moyen | 0.041 ms | 0.072 ms | QoS devrait être **bien plus bas** |
| Jitter P95 | 0.103 ms | 0.109 ms | QoS devrait être **bien plus bas** |
| Perte paquets | 0.0% | 0.0% | SANS QoS devrait avoir des pertes |
| Bandwidth moyen | 0.200 Mb/s | 0.200 Mb/s | Identique = aucune congestion |
| BW constant ? | Oui (toutes les sec) | Oui (sauf fin) | SANS QoS devrait varier |

Le flux de contrôle (200 Kbit/s sur un lien de 10 Mbit/s) passe parfaitement **dans les deux cas** parce qu'il n'y a aucune congestion. La cause : **le trafic de fond (car2 + car3 à 8M chacun) n'a pas été lancé** en même temps que le test iperf.[^3][^4]

Les logs iperf serveur confirment 0/17 datagrams perdus sur chaque intervalle de 1 seconde, pendant la totalité des 120 secondes. C'est un réseau parfaitement à vide.[^4][^3]

***

## Problème 2 : `priority_enabled: false` Pendant le Test QoS

La commande `curl http://localhost:8080/health` exécutée pendant (ou juste après) le test iperf « AVEC QoS » retourne :

```
{"status": "ok", "priority_enabled": false}
```

Cela signifie que **Ryu n'avait PAS activé la priorité** au moment du test réseau. Les règles `set_queue:1` pour UDP:9999 n'étaient pas en place.[^5]

### Pourquoi ?

L'orchestrateur SUMO a bien tourné et posté des métriques à Ryu (les logs Ryu montrent les POST `/metrics` et les messages `Installed priority rule`). Mais la simulation SUMO s'est terminée **avant** le test iperf :[^6]

- SUMO a fini à t=3453s (≈57 min), l'orchestrateur s'est arrêté
- Quand l'orchestrateur s'arrête, il ne poste plus de métriques `busy`
- Les prochains POST avec `busy < 3.0` (ou l'absence de POST) font que Ryu repasse `priority_enabled: false` et retire les règles[^5]

La commande `sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue` ne retourne rien, ce qui confirme qu'aucune règle de priorité n'existait au moment du test[^5].

***

## Problème 3 : Configuration SUMO Inadaptée

Le fichier `one_junction.sumocfg` référence `locked.rou.xml` qui contient 928 véhicules (4 × 232) répartis sur 1200 secondes. Mais la commande lancée utilise `--end 3600`, ce qui fait tourner SUMO 3600 secondes alors que les véhicules arrivent seulement entre 0 et 1200s. Après ~1200s, les queues tombent à 0, le `busy` descend sous 3.0, et Ryu désactive la priorité.[^7][^8][^5]

Le TLS défini dans `one_junction.add.xml` a 4 phases (2 vertes de 31s, 2 jaunes de 5s), et l'orchestrateur force correctement `--ns-phase-idx 0 --ew-phase-idx 2`. Cette partie fonctionne.[^9]

***

## Ce Qu'il Faut Refaire

### Étape corrigée pour le test AVEC QoS

Le test iperf doit tourner **en même temps** que SUMO + l'orchestrateur, et **pendant que le trafic de fond sature le lien**. Voici l'ordre correct à suivre dans **3 terminaux** :

**Terminal 1 — Ryu (ne change pas) :**

```bash
cd ~/experiments
ryu-manager ryu_qos_rest.py
```

**Terminal 2 — Mininet avec QoS + tests réseau :**

```bash
cd ~/experiments
sudo python3 traffic_topology_corridor.py \
  --bw-backhaul 10 --delay-backhaul 10ms --loss-backhaul 0.2 \
  --configure-qos
```

Puis dans le prompt `mininet-wifi>`, **attendre que l'orchestrateur ait posté des métriques** (voir Terminal 3), puis lancer **tout d'un coup** :

```
edge iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_qos.log &
edge iperf -s -u -p 5001 > /tmp/bg_server_qos.log &
car2 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car3 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1 &
```

**Terminal 3 — SUMO + orchestrateur :**

```bash
cd ~/experiments/sumo_one_junction
sumo -c one_junction.sumocfg \
  --remote-port 8813 \
  --end 3600 \
  --seed 42 \
  --time-to-teleport -1 &

sleep 3

cd ~/experiments
python3 tls_orchestrator_CORRECTED.py \
  --sumo-port 8813 \
  --tls-id J1 \
  --ns-phase-idx 0 \
  --ew-phase-idx 2 \
  --min-green 10 \
  --max-green 45 \
  --hysteresis 0.15 \
  --post-url http://localhost:8080/metrics
```

**⚠️ Point critique** : lancer les commandes iperf dans Mininet **pendant que les queues SUMO sont > 8** (l'orchestrateur affiche `NS=8, EW=8` autour de t=35s). Vérifier avec :

```bash
curl http://localhost:8080/health
```

Le résultat doit être `"priority_enabled": true` **AVANT** de lancer les iperf. Vérifier aussi :

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue
```

Cela doit afficher des lignes avec `udp,tp_dst=9999 actions=set_queue:1,NORMAL`.[^5]

### Étape corrigée pour le test SANS QoS

Même principe : le trafic de fond DOIT tourner en même temps :

```
edge iperf -s -u -p 9999 -i 1 > /tmp/ctrl_server_noqos.log &
edge iperf -s -u -p 5001 > /tmp/bg_server.log &
car2 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car3 iperf -c 10.0.0.254 -u -p 5001 -b 8M -t 120 &
car1 iperf -c 10.0.0.254 -u -p 9999 -b 200k -t 120 -i 1 &
```

**Sans trafic de fond, le lien de 10 Mbit/s n'est jamais saturé**, et il n'y a aucune raison d'observer de la congestion ni des pertes.[^4]

***

## Checklist Avant de Relancer

| Vérification | SANS QoS | AVEC QoS |
|---|---|---|
| Topologie lancée avec `--bw-backhaul 10` | ✅ Obligatoire | ✅ Obligatoire |
| Option `--configure-qos` | ❌ Non | ✅ Oui[^10] |
| `pingall` réussit | ✅ | ✅ |
| Trafic de fond (car2 + car3 à 8M chacun) | ✅ **EN MÊME TEMPS** que car1 | ✅ **EN MÊME TEMPS** que car1 |
| Orchestrateur SUMO | ❌ Non lancé | ✅ Lancé avec `--post-url`[^6] |
| `curl /health` → `priority_enabled` | `false` (normal) | **`true` obligatoire**[^5] |
| `dump-flows \| grep set_queue` | Rien (normal) | **Doit afficher set_queue:1** |
| Attendre 120s sans rien toucher | ✅ | ✅ |
| Fichier serveur = `ctrl_server_*.log` | ✅ `/tmp/ctrl_server_noqos.log` | ✅ `/tmp/ctrl_server_qos.log` |

***

## Résultats Attendus Après Correction

Avec le trafic de fond saturant le lien (16 Mbit/s pour 10 Mbit/s de capacité), les résultats devraient ressembler à :

| Métrique | SANS QoS (prévu) | AVEC QoS (prévu) |
|----------|-------------------|-------------------|
| Jitter moyen | 5–50 ms | < 1 ms |
| Perte paquets | 10–40% | < 5% |
| Bandwidth flux ctrl | Instable, chute | Stable ~200 Kbit/s |

Les fichiers SUMO (`one_junction.net.xml`, `one_junction.add.xml`, `locked.rou.xml`, etc.) sont corrects et n'ont pas besoin de modification. Le problème est uniquement dans **l'exécution des tests réseau** (timing et absence de trafic de fond).[^11][^8][^9]

---

## References

1. [ctrl_qos.json](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/c324665c-2a72-4ea0-bf69-2896012658ab/ctrl_qos.json?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=bbvHhFkFFgmJeQft%2BhK5Y1vRTpw%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - {
  "summary": {
    "samples": 121,
    "duration_s": 120.0687,
    "bw_mbps_mean": 0.2001900826446...

2. [ctrl_noqos.json](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/4306540a-31d3-457e-8fdc-470584982892/ctrl_noqos.json?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=hreljwYqdLexrfoYLDnEDgqp6O4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - {
  "summary": {
    "samples": 121,
    "duration_s": 120.0703,
    "bw_mbps_mean": 0.2001900826446...

3. [ctrl_server_qos.log](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/7c06526f-ef22-4d73-9448-d563f433b298/ctrl_server_qos.log?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=RyYdsjKafUdsn5E8gnSoA0w%2FCuQ%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - ------------------------------------------------------------
Server listening on UDP port 9999
UDP b...

4. [ctrl_server_noqos.log](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/a23bbbbd-9d08-4e65-978b-953296f90ce3/ctrl_server_noqos.log?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=Hv3aKVyxuxYGHi2WIWUccHmDH2I%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - ------------------------------------------------------------
Server listening on UDP port 9999
UDP b...

5. [ryu_qos_rest.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/48ad8f09-30cd-4297-ad28-0e2b5ea25593/ryu_qos_rest.py?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=%2B%2FYAtKPfh5t7TCNrE0QbIOLLHMc%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ryu QoS REST app (OpenFlow 1.3)

Purpose
-------
...

6. [tls_orchestrator_CORRECTED.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/b0101a47-b348-490b-99dd-30fbfa776de3/tls_orchestrator_CORRECTED.py?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=fSUdUlqHfRlp3WIvSqaZvNtooGE%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive TLS Orchestrator - VERSION CORRIGÉE

BUG...

7. [one_junction.sumocfg](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/1ee7165a-8dc4-420e-bc99-9911eda6d46c/one_junction.sumocfg?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=A7mqWIChwVZA5O2BewK84DQRgy4%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453)

8. [locked.rou.xml](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/a3843bbc-a90d-412e-ac23-6e2b3d308c1a/locked.rou.xml?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=wIObtA%2FkHk4hVgGtieFh1YaAhRs%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453)

9. [one_junction.add.xml](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/8659bf1e-01a7-4f4d-a693-6b9cc0a3f43d/one_junction.add.xml?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=nK9pWxV8%2BcYNm3w7vTHHSdH30Bk%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453)

10. [traffic_topology_corridor.py](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/fc55248c-20ae-485f-b61a-a165aa39a9ea/traffic_topology_corridor.py?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=QAWjlGwhv2eWbfLYn4f72GVNuhw%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453) - #!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traffic_topology_corridor.py
--------------------...

11. [one_junction.net.xml](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60545926/d7810eb8-af0c-4e07-a743-af364484ced7/one_junction.net.xml?AWSAccessKeyId=ASIA2F3EMEYEWJJEVONB&Signature=VqFVU8KoFkJsHND4safW989iahg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEIz%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJIMEYCIQDjJWhxYAEmR06HNnzanAgUu%2Fxx2SiXVA1VZ8hNoAtzFAIhAP%2FjPWPuQYhVKhU29ydhNZFUYOwDZ3hq9iNtsOqt6BBTKvMECFUQARoMNjk5NzUzMzA5NzA1IgwoxaRAs%2FUajTGLn2sq0ATHP3lqYbFEoepFxRPl2STT0qU2NtcidMxtQt4uzm5kWfWY%2FR9btXK7Zv4V%2FlFiqZARqlmezP520aFNOS%2BlDH%2Fd%2FDLkh1o6tRqMShaJ7lYsXTVnbouiWXp0K0hA3vJA0aL%2FgRzk1321d7LMys%2F2fe8UuNQmw3ROQShJnzQiboktlyMAhK%2B6WLhEtnGO1quVdfoLhAjySrRfbJ2WQB8FEzbauUqk9JxzCcipfBFqDKc5tUhhp5TJw%2BdRf3eD73%2BO3DbMBemfCWISWF7iUIsRsLalGJgkFTVJVMWsrzvJJTI2nOUcGt4fL4xsUySrUgAa%2FcsIkdmHqPPHq2kgi1llTXOlWrYAd2PhMOhWWhMxZUHGa%2BcE%2BC98POqYQrUb2sAOQL0xMCTnHFXpcWvNcUIgIv0MAi6biMQOvaPeeRvHs3hExLVZJLh1kCxrdXZYkSnoMRWw%2BhBiIRe96neoqOagJFx22oq2hMXzMTszXpAAyrzxnkHNkWsXc6sB56fZ8GDaC4XA4ftpDJumBwhp8h5A0oG12w2Hkf6BTuQ7AImie%2FCrCEdzmBfl9Brs451kRk6QIref4oeJy30WOaly72Tnai97ImcthcHd%2FcDKXsdyrd4%2FIfyo7kUpSQW6XqF6IYzA3J4Lxp81fIRhdGv4KKwy52%2FYpbehQGduczCwS0N3gcCpstHdSkpP5f1RJaMGSThFEy0sE%2BOgBEs0EM4pHBj4wedz4l6VxJRgQbnhegK2nsFgod6SsE5vajFh8DnVi0mtBIitftGAEFkGrZB4Fr7aucSUMKGmi80GOpcBjP2BPaoG%2B%2Fa7CVXVm8Ab52%2FFk5MjCXsVBZUTXkCM1XweC0cgx8hyMCYDiu4epVCqL%2FnAbsEUpnRsoGIA8JXrrDch9ZCk5vmR9apDRQM3Ic%2BjQMPshiX4tDpZGxBM71%2Fgk7%2FOJuq6SCE3Iamnqcxr4iPSIZ0PKN6Xg%2Bc6URRTAsgbB4nDTClMGxed1u6gdoOcaVxDzLjx2Q%3D%3D&Expires=1772282453)

