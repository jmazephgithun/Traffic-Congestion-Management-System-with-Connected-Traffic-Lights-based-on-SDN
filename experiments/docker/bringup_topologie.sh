#!/bin/bash
# Reconstruit, sans Mininet-WiFi (mac80211_hwsim indisponible dans ce conteneur),
# la seule partie de traffic_topology_corridor.py que le Test B mesure reellement :
# trois stations (car1 = flux de controle, car2/car3 = trafic de fond) associees a
# ap1, ap1 relie a edge par un lien reduit a --bw-edge Mbit/s avec --delay-edge de
# delai, deux files HTB sur ce port (queue 0 = best-effort, queue 1 = prioritaire),
# et ap1 controle par le Ryu reel (ryu_qos_rest.py, fichier non modifie).
#
# Le remplacement des stations WiFi par des espaces de noms reseau ne change rien
# a ce que le test mesure : la priorisation OpenFlow et les files HTB d'Open vSwitch,
# pas la couche radio. C'est explicitement assume dans le README du dossier docker/.
set -e

BW_EDGE=${BW_EDGE:-5}
DELAY_EDGE=${DELAY_EDGE:-5ms}

echo "[bringup] demarrage d'Open vSwitch (datapath netdev, espace utilisateur)"
mkdir -p /var/run/openvswitch /etc/openvswitch /var/log/openvswitch
if [ ! -f /etc/openvswitch/conf.db ]; then
    ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
fi
ovsdb-server --remote=punix:/var/run/openvswitch/db.sock --pidfile --detach --log-file
ovs-vsctl --no-wait init
ovs-vswitchd --pidfile --detach --log-file

echo "[bringup] creation du pont ap1"
ovs-vsctl --may-exist add-br ap1 -- set bridge ap1 datapath_type=netdev protocols=OpenFlow13
ovs-vsctl set-controller ap1 tcp:127.0.0.1:6653

echo "[bringup] creation des espaces de noms car1, car2, car3, edge"
for ns in car1 car2 car3 edge; do
    ip netns add "$ns" 2>/dev/null || true
done

declare -A IP=( [car1]=10.0.0.1 [car2]=10.0.0.2 [car3]=10.0.0.3 [edge]=10.0.0.254 )
for ns in car1 car2 car3 edge; do
    veth_h="ap1-${ns}"
    veth_ns="${ns}-eth0"
    ip link add "$veth_h" type veth peer name "$veth_ns" 2>/dev/null || true
    ip link set "$veth_ns" netns "$ns"
    ip netns exec "$ns" ip addr add "${IP[$ns]}/24" dev "$veth_ns"
    ip netns exec "$ns" ip link set "$veth_ns" up
    ip netns exec "$ns" ip link set lo up
    ip link set "$veth_h" up
    ovs-vsctl --may-exist add-port ap1 "$veth_h"
done

echo "[bringup] regle de base : NORMAL pour tout paquet (priority=0)"
ovs-ofctl -O OpenFlow13 add-flow ap1 "priority=0,actions=NORMAL"

echo "[bringup] limitation et files HTB sur le port ap1-edge (${BW_EDGE} Mbit/s, ${DELAY_EDGE})"
# netem et linux-htb ne peuvent pas etre deux qdisc racines du meme port.
# Le delai est donc applique sur l'extremite edge, tandis qu'OVS gere HTB sur ap1-edge.
ip netns exec edge tc qdisc replace dev edge-eth0 root netem delay "$DELAY_EDGE"
MAX_RATE=$((BW_EDGE * 1000 * 1000))
DFLT_MAX=$((BW_EDGE * 1000 * 1000))
PRIO_MIN=$((BW_EDGE * 1000 * 700))
ovs-vsctl -- set port ap1-edge qos=@q \
  -- --id=@q create qos type=linux-htb other-config:max-rate=$MAX_RATE queues:0=@dflt queues:1=@prio \
  -- --id=@dflt create queue other-config:min-rate=100000 other-config:max-rate=${DFLT_MAX} \
  -- --id=@prio create queue other-config:min-rate=${PRIO_MIN} other-config:max-rate=${MAX_RATE}

echo "[bringup] pret. Verification de connectivite (equivalent pingall) :"
for ns in car1 car2 car3; do
    ip netns exec "$ns" ping -c 1 -W 2 10.0.0.254 >/dev/null 2>&1 \
      && echo "  $ns -> edge : ok" \
      || echo "  $ns -> edge : ECHEC"
done
