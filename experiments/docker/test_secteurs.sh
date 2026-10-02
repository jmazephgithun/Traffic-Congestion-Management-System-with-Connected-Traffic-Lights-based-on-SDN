#!/usr/bin/env bash
# Niveau 2 : prototype de controleurs par secteur avec secours (chapitre 3, section 7).
#
# Deux secteurs, Abidjan Nord et Abidjan Sud, sont emules chacun par un pont
# Open vSwitch (carrefour) relie a trois vehicules et a un noeud edge, comme en
# phase B. Chaque pont est rattache a DEUX controleurs Ryu executant le meme
# ryu_qos_rest.py : un principal et un secours.
#
#   secteur  pont     principal (OpenFlow/REST)   secours (OpenFlow/REST)
#   Nord     apnord   6653 / 8080                 6654 / 8081
#   Sud      apsud    6655 / 8082                 6656 / 8083
#
# Le test verifie, dans l'ordre :
#   1. les deux ponts sont connectes a leurs deux controleurs ;
#   2. la connectivite des vehicules de chaque secteur ;
#   3. la panne du principal Nord : le secours prend la main, la regle de
#      priorite est installee par le secours et la connectivite est conservee ;
#   4. le secteur Sud n'est pas affecte par la panne du secteur Nord ;
#   5. la panne des deux controleurs Nord : le pont passe en mode autonome
#      (fail_mode standalone) et l'acheminement continue sans priorisation.
#
# Sortie : results_docker/secteurs.json et les journaux dans results_docker/secteurs/.
set -euo pipefail
cd /experiments
OUT=/experiments/results_docker
LOGS=$OUT/secteurs
mkdir -p "$LOGS"
rm -f "$LOGS"/*.log

ok()   { echo "[OK] $*"; }
fail() { echo "[ECHEC] $*" >&2; exit 1; }
now()  { date +%s.%N; }

# Datapath noyau (celui de Mininet) si le module openvswitch est charge sur l'hote :
# c'est le seul ou l'action set_queue choisit reellement la file HTB. A defaut,
# repli sur le datapath en espace utilisateur (netdev), qui conserve la
# commutation et OpenFlow mais ignore set_queue : la QoS n'y est pas mesurable.
if [ -z "${DATAPATH:-}" ]; then
    if [ -d /sys/module/openvswitch ]; then DATAPATH=system; else DATAPATH=netdev; fi
fi
echo "$DATAPATH" > "$LOGS/datapath.txt"
echo "[secteurs] demarrage d'Open vSwitch"
mkdir -p /var/run/openvswitch /etc/openvswitch /var/log/openvswitch
[ -f /etc/openvswitch/conf.db ] || ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
ovsdb-server --remote=punix:/var/run/openvswitch/db.sock --pidfile --detach --log-file
ovs-vsctl --no-wait init
ovs-vswitchd --pidfile --detach --log-file

declare -A PID
lancer_ryu() { # nom port_openflow port_rest
  ryu-manager --ofp-tcp-listen-port "$2" --wsapi-port "$3" pyfilesTrue/ryu_qos_rest.py >"$LOGS/ryu_$1.log" 2>&1 &
  PID[$1]=$!
}
lancer_ryu nord_principal 6653 8080
lancer_ryu nord_secours   6654 8081
lancer_ryu sud_principal  6655 8082
lancer_ryu sud_secours    6656 8083
for port in 8080 8081 8082 8083; do
  for _ in $(seq 1 30); do curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1 && break; sleep 1; done
  curl -fsS "http://127.0.0.1:$port/health" >/dev/null || fail "Ryu sur le port REST $port ne repond pas"
done
ok "quatre controleurs Ryu demarres (Nord et Sud, principal et secours)"

construire_secteur() { # pont prefixe sous-reseau port_principal port_secours
  local br=$1 pre=$2 net=$3
  ovs-vsctl --may-exist add-br "$br" -- set bridge "$br" datapath_type=$DATAPATH protocols=OpenFlow13 fail_mode=standalone
  ovs-vsctl set-controller "$br" "tcp:127.0.0.1:$4" "tcp:127.0.0.1:$5"
  # Detection rapide de la perte d'un controleur (sonde d'inactivite d'une seconde).
  for c in $(ovs-vsctl get bridge "$br" controller | tr -d '[],'); do
    ovs-vsctl set controller "$c" inactivity_probe=1000 max_backoff=1000
  done
  local i=1
  for h in car1 car2 car3 edge; do
    local ns="${pre}${h}" ip="10.0.${net}.${i}"
    [ "$h" = edge ] && ip="10.0.${net}.254"
    ip netns add "$ns" 2>/dev/null || true
    ip link add "${pre}-${h}" type veth peer name eth0 netns "$ns"
    ip netns exec "$ns" ip addr add "$ip/24" dev eth0
    ip netns exec "$ns" ip link set eth0 up
    ip netns exec "$ns" ip link set lo up
    ip link set "${pre}-${h}" up
    ovs-vsctl add-port "$br" "${pre}-${h}"   # ofport 1..4 : edge reste le port 4, comme en phase B
    ethtool -K "${pre}-${h}" tx off >/dev/null              # sommes de controle UDP calculees en logiciel
    ip netns exec "$ns" ethtool -K eth0 tx off >/dev/null
    i=$((i + 1))
  done
  ovs-vsctl -- set port "${pre}-edge" qos=@q \
    -- --id=@q create qos type=linux-htb other-config:max-rate=5000000 queues:0=@d queues:1=@p \
    -- --id=@d create queue other-config:min-rate=100000 other-config:max-rate=5000000 \
    -- --id=@p create queue other-config:min-rate=3500000 other-config:max-rate=5000000 >/dev/null
}
construire_secteur apnord n 1 6653 6654
construire_secteur apsud  s 2 6655 6656

connectes() { # pont -> nombre de controleurs connectes
  ovs-vsctl --bare --columns=is_connected list controller $(ovs-vsctl get bridge "$1" controller | tr -d '[],') | grep -c true || true
}
for _ in $(seq 1 30); do
  [ "$(connectes apnord)" = 2 ] && [ "$(connectes apsud)" = 2 ] && break; sleep 1
done
[ "$(connectes apnord)" = 2 ] || fail "apnord n'est pas connecte a ses deux controleurs"
[ "$(connectes apsud)" = 2 ]  || fail "apsud n'est pas connecte a ses deux controleurs"
ok "chaque pont est connecte a son principal et a son secours"

ping_ok() { ip netns exec "$1" ping -c 2 -W 2 "$2" >/dev/null 2>&1; }
ping_ok ncar1 10.0.1.254 || fail "Nord : car1 ne joint pas edge"
ping_ok scar1 10.0.2.254 || fail "Sud : car1 ne joint pas edge"
ok "connectivite des deux secteurs"

regle_presente() { ovs-ofctl -O OpenFlow13 dump-flows "$1" | grep -q 'tp_dst=9999.*set_queue:1'; }

# Orchestrateur configure avec deux adresses : il publie au principal et bascule
# sur le secours des que le principal ne repond plus (delai d'attente 0,5 s).
publier() { # busy url_principale url_secours
  curl -fsS -m 0.5 -H 'Content-Type: application/json' -d "{\"busy\":$1}" "$2/metrics" 2>/dev/null \
    || curl -fsS -m 0.5 -H 'Content-Type: application/json' -d "{\"busy\":$1}" "$3/metrics"
}
NORD1=http://127.0.0.1:8080; NORD2=http://127.0.0.1:8081
SUD1=http://127.0.0.1:8082;  SUD2=http://127.0.0.1:8083

publier 20 $NORD1 $NORD2 | jq -e '.priority == true' >/dev/null
sleep 1
regle_presente apnord || fail "Nord : le principal n'a pas installe la regle de priorite"
publier 0 $NORD1 $NORD2 >/dev/null; sleep 1
regle_presente apnord && fail "Nord : la regle n'a pas ete retiree"
ok "Nord : le principal commande la priorite (activation puis retrait)"

echo "[secteurs] panne du controleur principal Nord"
ip netns exec ncar1 ping -i 0.2 -c 50 10.0.1.254 >"$LOGS/ping_nord_pendant_panne.log" 2>&1 & ping_pid=$!
sleep 0.5
t0=$(now)
kill -9 "${PID[nord_principal]}"; wait "${PID[nord_principal]}" 2>/dev/null || true
# L'orchestrateur continue de publier chaque 0,2 s ; il retombe sur le secours.
for _ in $(seq 1 100); do
  publier 20 $NORD1 $NORD2 >/dev/null 2>&1 || true
  regle_presente apnord && break
  sleep 0.2
done
t1=$(now)
regle_presente apnord || fail "Nord : le secours n'a pas installe la regle de priorite"
bascule=$(python3 -c "print(round($t1 - $t0, 2))")
curl -fsS $NORD2/health | jq -e '.priority_enabled == true' >/dev/null || fail "Nord : le secours n'a pas pris la decision"
for _ in $(seq 1 10); do [ "$(connectes apnord)" = 1 ] && break; sleep 1; done
[ "$(connectes apnord)" = 1 ] || fail "Nord : OVS ne detecte pas la perte du principal"
wait "$ping_pid" || true
pertes_bascule=$(grep -oE '[0-9]+% packet loss' "$LOGS/ping_nord_pendant_panne.log" | grep -oE '^[0-9]+' || echo 100)
ok "Nord : le secours a repris la main en ${bascule} s, pertes pendant la bascule : ${pertes_bascule} %"

ping_ok scar1 10.0.2.254 || fail "Sud : connectivite perdue pendant la panne Nord"
[ "$(connectes apsud)" = 2 ] || fail "Sud : un controleur a ete perdu pendant la panne Nord"
publier 20 $SUD1 $SUD2 | jq -e '.priority == true' >/dev/null; sleep 1
regle_presente apsud || fail "Sud : le principal ne commande plus la priorite"
ok "Sud : non affecte, son principal commande toujours la priorite"

echo "[secteurs] panne des deux controleurs Nord (mode degrade)"
kill -9 "${PID[nord_secours]}"; wait "${PID[nord_secours]}" 2>/dev/null || true
for _ in $(seq 1 10); do [ "$(connectes apnord)" = 0 ] && break; sleep 1; done
[ "$(connectes apnord)" = 0 ] || fail "Nord : OVS voit encore un controleur"
sleep 4   # au-dela de trois sondes d'inactivite : le pont applique son fail_mode
ping_ok ncar1 10.0.1.254 || fail "Nord : pas d'acheminement en mode degrade"
ok "Nord : sans controleur, le pont achemine en mode autonome (fail_mode=standalone)"

cat >"$OUT/secteurs.json" <<JSON
{
  "secteurs": ["Abidjan Nord", "Abidjan Sud"],
  "controleurs_par_secteur": 2,
  "bascule_s": $bascule,
  "pertes_ping_pendant_bascule_pct": $pertes_bascule,
  "sud_affecte_par_panne_nord": false,
  "mode_degrade_connectivite": true
}
JSON
for p in "${PID[@]}"; do kill "$p" 2>/dev/null || true; done
echo "[SUCCES] controleurs par secteur avec secours -> $OUT/secteurs.json"
