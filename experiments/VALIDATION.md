# Rapport de validation réelle

Date d’exécution : **2 octobre 2026**
Environnement : Docker 29.5, Docker Compose v5.1, hôte WSL 2 (noyau Linux 6.18) avec le
module `openvswitch` chargé ; datapath Open vSwitch utilisé en phase B : `system`.

Ce document rapporte uniquement des observations produites par les commandes du dépôt.
Les fichiers détaillés sont générés dans `results_docker/` et exclus de Git.

## Commandes exécutées

```bash
make build
make test
make test-a3 && make evaluate-30 && make test-a1w
make test-b1 && make test-b2
make test-c && make test-c30
make rapport
make test-secteurs
make demo && make replay && make test-solibra
```

Toutes ces commandes se sont terminées avec le code de sortie `0`. Tests unitaires : 4/4 réussis.

## Niveau 1 : comparaison avec le mémoire

### Phase A, tableau 3.4 (graine 42)

| Indicateur | Mémoire, feux fixes | Docker, feux fixes | Mémoire, adaptatif | Docker, adaptatif |
|---|---:|---:|---:|---:|
| Véhicules écoulés sur 1 300 | 974 | 974 | 1 300 | 1 300 |
| Véhicules bloqués | 326 | 326 | 0 | 0 |
| Durée moyenne de trajet (s) | 169,1 | 169,1 | 169,0 | 169,0 |
| Temps perdu moyen (s) | 154,0 | 154,0 | 153,8 | 153,8 |

### Phase A, trente graines appariées et plan Webster

| Mesure | Mémoire | Docker |
|---|---:|---:|
| Véhicules bloqués en feux fixes, moyenne | 25,11 % | 25,11 % |
| IC 95 % | [24,97 ; 25,25] | [24,98 ; 25,24] |
| Complétion en feux adaptatifs | 100 % | 100 % |
| Complétion du plan Webster | 76,5026 % | 76,5026 % |
| IC 95 % du plan Webster | [76,4123 ; 76,5928] | [76,4123 ; 76,5928] |

La phase A est reproduite à l’identique : SUMO est déterministe à graine donnée.

### Point de vigilance méthodologique : l’horizon de simulation

En reproduisant la phase A, le banc a mis en évidence une différence d’horizon entre les
deux variantes du protocole du mémoire. Les feux fixes sont simulés jusqu’à 3 600 s
(`--end 3600`), tandis qu’en mode adaptatif l’orchestrateur fait avancer SUMO jusqu’à ce
que tous les véhicules soient sortis. Mesures sur la graine 42 :

| Horizon | Feux fixes | Plan Webster | Feux adaptatifs |
|---|---:|---:|---:|
| 3 600 s, identique pour tous | 974 / 1 300 | non mesuré | 979 / 1 300 |
| 4 800 s | 1 298 / 1 300 | 1 300 / 1 300 | 1 300 / 1 300 (dernier véhicule à 4 789 s) |

Les 326 véhicules non écoulés en feux fixes à 3 600 s ne sont donc pas bloqués
définitivement : ils sont encore en file et sortent ensuite. À horizon égal, l’écart entre
les deux politiques est de quelques véhicules. Le banc conserve volontairement le
protocole du mémoire, pour en reproduire les valeurs publiées ; une comparaison à
horizon égal, avec des indicateurs comme le temps total passé dans le réseau ou la
longueur maximale des files, permettrait de mesurer l’apport réel de la commande
adaptative.

### Phase B, tableau 3.5 (120 s, flux de contrôle à 200 kbit/s, 16 Mbit/s de fond sur 5 Mbit/s)

| Mesure côté récepteur | Mémoire, sans QoS | Docker, sans QoS | Mémoire, avec QoS | Docker, avec QoS |
|---|---:|---:|---:|---:|
| Pertes moyennes | 69,6 % | 62,8 % | 0 % | 0 % |
| Débit utile reçu (Mbit/s) | 0,056 | 0,039 | 0,200 | 0,192 |
| Jitter moyen (ms) | 110,31 | 15,06 | 0,06 | 0,42 |

Les pertes et le débit utile sont du même ordre que dans le mémoire, et l’effet de la QoS
est le même : elle supprime les pertes du flux de commande et lui rend la quasi-totalité
de son débit. Le jitter absolu sans QoS est plus faible ici : le banc Docker émule le
point d’accès par une file FIFO courte (50 paquets), qui retarde peu les paquets ; le
point d’accès Wi-Fi émulé par Mininet-WiFi accumulait davantage de retard.

Trois corrections ont été nécessaires pour obtenir ces mesures (voir README, section 3.2) :
sommes de contrôle UDP calculées en logiciel sur les paires veth, datapath noyau
d’Open vSwitch (le datapath en espace utilisateur ignore `set_queue`), et files FIFO
explicites sous les classes HTB. Avant ces corrections, le récepteur ne recevait aucun
paquet UDP et la version précédente de ce rapport ne pouvait conclure sur la phase B.

### Boucle fermée

- Exécution intégrée, graine 42 : 113 changements de phase, installation de la règle
  prioritaire par Ryu observée dans `ryu.log`.
- Décision d’hystérésis sur 30 graines : priorité activée dans les 30 exécutions, active
  99,32 % du temps en moyenne (minimum 98,73 %, maximum 99,66 %), première activation à
  2 s de simulation.

## Niveau 2 : option évoluée

### Contrôleurs par secteur avec secours (`make test-secteurs`)

| Vérification | Résultat |
|---|---|
| Chaque pont connecté à son principal et à son secours | réussi |
| Le principal Nord commande la priorité (activation puis retrait) | réussi |
| Arrêt brutal du principal Nord : le secours installe la règle | réussi, en 0,02 s |
| Pertes de ping pendant la bascule | 0 % |
| Secteur Sud pendant la panne Nord | non affecté |
| Arrêt des deux contrôleurs Nord : acheminement en mode autonome | réussi |

La bascule est quasi immédiate car l’orchestrateur détecte le refus de connexion du
principal et publie aussitôt au secours, déjà connecté au commutateur.

### Démonstration sur le carrefour réel de Solibra (`make demo`, graine 42, 1 800 s)

| Mesure | Feux fixes | Feux adaptatifs |
|---|---:|---:|
| Véhicules arrivés sur 5 852 injectés | 2 150 (36,7 %) | 2 414 (41,3 %) |
| Pic de véhicules à l’arrêt | 139 | 110 |

L’écart est plus modeste qu’au carrefour J1 : la demande recalibrée dépasse la capacité
du carrefour sur les deux axes à la fois. La commande adaptative améliore l’écoulement,
elle ne crée pas de capacité.

### Campagne Solibra sur trente graines (`make test-solibra`)

| Mesure (30 graines, protocole du mémoire) | Feux fixes | Feux adaptatifs |
|---|---:|---:|
| Complétion | 73,81 % (IC 95 % [73,78 ; 73,83]) | 100 % |
| Gain apparié | | 26,19 points (IC 95 % [26,17 ; 26,22]) |

Ces valeurs suivent le protocole du mémoire et appellent la même réserve d’horizon que
la phase A (voir le point de vigilance ci-dessous).

## Limites

- Simulation (SUMO) et émulation réseau (espaces de noms Linux, Open vSwitch) : la radio
  Wi-Fi n’est pas modélisée par ce banc.
- La demande n’est calibrée sur aucun comptage réel.
- Le prototype par secteur valide le mécanisme de basculement sur deux ponts émulés ; il
  ne dimensionne pas un réseau de plusieurs centaines de carrefours.
