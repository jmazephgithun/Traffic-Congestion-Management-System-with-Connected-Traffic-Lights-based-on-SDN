# Rapport de validation réelle

Date d’exécution : **31 août 2026**  
Version validée : branche `main`, base `e9fd9b1`  
Environnement : Docker Compose sous Linux, scénario par défaut `BW_EDGE=5` et `DELAY_EDGE=5ms`.

Ce document rapporte uniquement les observations produites par les commandes du dépôt. Les fichiers détaillés sont générés localement dans `results_docker/` et sont volontairement exclus de Git.

## Commandes exécutées

```bash
docker compose build
docker compose run --rm tests
make test-a3
make test-b1
make test-b2
make test-c
```

Toutes ces commandes se sont terminées avec le code de sortie `0`.

## Tests unitaires et construction

| Vérification | Résultat observé |
|---|---:|
| Construction de l’image | Réussie |
| Validation Compose | Réussie |
| Tests unitaires | 3/3 réussis |
| Analyseur iperf | Réussi |
| Analyseur SUMO | Réussi |
| Parseur de graines | Réussi |

## Phase A — mobilité, graine 42

Le test A3 a injecté 1 300 véhicules dans chaque variante.

| Mesure | Baseline fixe | Adaptatif |
|---|---:|---:|
| Véhicules terminés | 974 | 1 300 |
| Véhicules bloqués | 326 | 0 |
| Taux de complétion | 74,9231 % | 100 % |
| Durée moyenne | 169,1006 s | 169,0069 s |
| Attente moyenne | 81,6068 s | 82,0769 s |
| Temps perdu moyen | 153,9579 s | 153,8373 s |

Le gain observé est de **25,0769 points de complétion**. Cette exécution utilise une seule graine : elle valide le fonctionnement et fournit un cas reproductible, mais ne constitue pas à elle seule une preuve statistique. La commande `make evaluate-30` est prévue pour la campagne appariée de 30 graines.

## Phase B — réseau sans et avec QoS

Les deux scénarios ont produit neuf intervalles iperf exploitables sur environ huit secondes.

| Mesure côté client | Sans QoS | Avec QoS |
|---|---:|---:|
| Débit moyen émis | 1,0522 Mbit/s | 1,0522 Mbit/s |
| P5 | 1,05 Mbit/s | 1,05 Mbit/s |
| P95 | 1,06 Mbit/s | 1,06 Mbit/s |

Les validations fonctionnelles suivantes ont réussi : API Ryu disponible, quatre namespaces connectés, activation par `busy=20`, installation de `set_queue:1`, paquets comptés par la règle prioritaire, puis désactivation par hystérésis.

### Interprétation correcte

Ces journaux clients prouvent la génération stable du flux, mais **ne démontrent pas une réduction du jitter ou des pertes** : iperf2 calcule ces deux métriques côté serveur et les journaux serveur de cette exécution ne contiennent pas de résumé exploitable. Les valeurs sans/avec QoS étant identiques côté émetteur, aucune amélioration de performance réseau ne doit être revendiquée sur cette seule mesure. Une future campagne devra fiabiliser la collecte côté récepteur et répéter B1/B2 sur plusieurs graines ou répétitions.

## Phase C — boucle fermée

La chaîne complète a été exécutée avec succès :

```text
SUMO -> orchestrateur -> POST /metrics -> Ryu -> OpenFlow -> OVS/HTB
```

Observations :

- **113** changements de phase dans le journal de l’orchestrateur ;
- **1** installation de règle prioritaire observée dans le journal Ryu ;
- connectivité de `car1`, `car2` et `car3` vers `edge` réussie ;
- fin du scénario avec code de sortie `0`.

## Conclusion

La conteneurisation, la mobilité adaptative, l’API Ryu, l’hystérésis, l’installation OpenFlow et la boucle fermée sont réellement exécutables. Le bénéfice de complétion de la phase A est observé sur la graine 42. La phase B valide actuellement le mécanisme QoS, mais sa preuve quantitative sur jitter/pertes reste à compléter avant inclusion comme résultat définitif du mémoire.

