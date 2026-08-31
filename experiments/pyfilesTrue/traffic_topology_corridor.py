#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
traffic_topology_corridor.py
--------------------------------
Mininet-WiFi corridor testbed:
- AP1 (OVS)  <wired backhaul>  AP2 (OVS)
- AP1 uplink to 'edge' host (10.0.0.254)
- Cars (stations) associate to APs
- Remote Ryu controller (default 127.0.0.1:6653)
- Optional OVS QoS HTB on wired ports (ap1-eth2, ap1-eth3, ap2-eth2)

Examples
--------
# vanilla (no QoS), 100 Mb/s backhaul, small delays
sudo python3 traffic_topology_corridor.py

# with QoS queues on wired ports (queue 1 = "priority")
sudo python3 traffic_topology_corridor.py --configure-qos

# tighter backhaul to make QoS effects more visible
sudo python3 traffic_topology_corridor.py --bw-backhaul 10 --delay-backhaul 10ms --loss-backhaul 0.2
"""

import argparse
from mininet.log import setLogLevel, info
from mininet.link import TCLink
from mn_wifi.net import Mininet_wifi
from mn_wifi.cli import CLI
from mn_wifi.node import OVSKernelAP
from mininet.node import RemoteController, OVSKernelSwitch

def sh(node, cmd):
    "run shell command on a node and echo it for debugging"
    info(f"{node.name}$ {cmd}\n")
    return node.cmd(cmd)

def attach_qos(port: str, max_rate_mbit: int,
               dflt_min_kbit=1000, dflt_max_kbit=None,
               prio_min_kbit=5000, prio_max_kbit=None):
    """
    Attach linux-htb QoS to an OVS port with 2 queues:
      - queue 0: default (best-effort)
      - queue 1: priority (for UDP:9999 when set by Ryu)
    """
    if dflt_max_kbit is None:
        dflt_max_kbit = int(max_rate_mbit * 1000 * 0.9)   # 90% of port
    if prio_max_kbit is None:
        prio_max_kbit = int(max_rate_mbit * 1000 * 1.0)   # full port

    cmd = (
        f'ovs-vsctl -- set port {port} qos=@q '
        f'-- --id=@q create qos type=linux-htb other-config:max-rate={max_rate_mbit*1000*1000} '
        f'queues:0=@dflt queues:1=@prio '
        f'-- --id=@dflt create queue other-config:min-rate={dflt_min_kbit*1000} other-config:max-rate={dflt_max_kbit*1000} '
        f'-- --id=@prio create queue other-config:min-rate={prio_min_kbit*1000} other-config:max-rate={prio_max_kbit*1000}'
    )
    return cmd

def build(args):
    net = Mininet_wifi(
        controller=RemoteController,
        link=TCLink,
        accessPoint=OVSKernelAP,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True
    )

    info('*** Controller\n')
    c0 = net.addController('c0', controller=RemoteController,
                           ip=args.ctrl_ip, port=args.ctrl_port)

    info('*** APs and stations\n')
    # positions in meters (x,y,z), AP ranges are generous to avoid “increase range” warnings
    ap1 = net.addAccessPoint('ap1', ssid='ap1-ssid', mode='g', channel='1',
                             position='0,0,0', range=120)
    ap2 = net.addAccessPoint('ap2', ssid='ap2-ssid', mode='g', channel='6',
                             position='90,0,0', range=120)

    car1 = net.addStation('car1', ip='10.0.0.1/24', position='5,0,0')
    car2 = net.addStation('car2', ip='10.0.0.2/24', position='12,0,0')
    car3 = net.addStation('car3', ip='10.0.0.3/24', position='20,0,0')

    edge = net.addHost('edge', ip='10.0.0.254/24')

    info('*** Wireless config\n')
    # realistic but stable propagation
    net.setPropagationModel(model="logDistance", exp=2.8)
    net.configureWifiNodes()

    info('*** Wired backhaul links with shaping\n')
    # AP1 <-> AP2 backhaul
    net.addLink(ap1, ap2,
                intfName1='ap1-eth2', intfName2='ap2-eth2',
                cls=TCLink,
                bw=args.bw_backhaul,            # Mbit/s
                delay=args.delay_backhaul,      # e.g., '5ms'
                loss=args.loss_backhaul)        # e.g., 0.1 (%)

    # AP1 <-> Edge uplink (fast/clean by default)
    net.addLink(ap1, edge,
                intfName1='ap1-eth3', intfName2='edge-eth0',
                cls=TCLink,
                bw=args.bw_edge,                # Mbit/s
                delay=args.delay_edge,
                loss=args.loss_edge)

    info('*** Build & start\n')
    net.build()
    c0.start()
    ap1.start([c0])
    ap2.start([c0])

    # Force OpenFlow13 and NORMAL table-miss on both AP bridges
    for ap in (ap1, ap2):
        sh(ap, f'ovs-vsctl set bridge {ap.name} protocols=OpenFlow13')
        # default table-miss so packets are bridged unless a higher-priority rule (e.g., Ryu set_queue) matches
        sh(ap, f'ovs-ofctl -O OpenFlow13 add-flow {ap.name} "priority=0,actions=NORMAL"')

    # ── OVS QoS on wired ports ─────────────────────────────────
    # Mininet's TCLink applies tc-htb on interfaces, but OVS kernel
    # datapath bypasses tc when forwarding between bridge ports.
    # We MUST use OVS-native QoS (ovs-vsctl set port … qos=…) to
    # enforce bandwidth limits that actually affect forwarded traffic.
    if args.configure_qos:
        # Full QoS: 2 queues (queue 0 = best-effort, queue 1 = priority)
        info('*** Attaching OVS QoS (HTB) queues on wired ports\n')
        cmds = [
            attach_qos('ap1-eth2', args.bw_backhaul),
            attach_qos('ap1-eth3', args.bw_edge),
            attach_qos('ap2-eth2', args.bw_backhaul),
        ]
        for ap, cmd in ((ap1, cmds[0]), (ap1, cmds[1]), (ap2, cmds[2])):
            sh(ap, cmd)
    else:
        # No priority queues, but still enforce rate limits via OVS QoS
        # so that bandwidth shaping actually works on OVS bridge ports.
        info('*** Attaching OVS rate-limits (single queue) on wired ports\n')
        for port, bw_mbit in [('ap1-eth2', args.bw_backhaul),
                               ('ap1-eth3', args.bw_edge),
                               ('ap2-eth2', args.bw_backhaul)]:
            max_rate = bw_mbit * 1000 * 1000   # bits/sec
            cmd = (
                f'ovs-vsctl -- set port {port} qos=@q '
                f'-- --id=@q create qos type=linux-htb '
                f'other-config:max-rate={max_rate} queues:0=@dflt '
                f'-- --id=@dflt create queue '
                f'other-config:max-rate={max_rate}'
            )
            sh(ap1 if 'ap1' in port else ap2, cmd)

    info('*** Mobility hint: you can extend ranges or move cars in CLI\n')
    info('*** Example:\n')
    info('    mininet> py ap1.setRange(120); ap2.setRange(120)\n')
    info('    mininet> py car1.setPosition("5,0,0")\n')
    info('*** Ready. Start iperf servers on edge; run clients from cars.\n')

    return net

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ctrl-ip', default='127.0.0.1', help='Ryu IP')
    ap.add_argument('--ctrl-port', type=int, default=6653, help='Ryu port')

    ap.add_argument('--bw-backhaul', type=int, default=100, help='AP1<->AP2 backhaul bandwidth (Mbit/s)')
    ap.add_argument('--delay-backhaul', default='5ms', help='AP1<->AP2 backhaul delay')
    ap.add_argument('--loss-backhaul', type=float, default=0.1, help='AP1<->AP2 backhaul loss (%)')

    ap.add_argument('--bw-edge', type=int, default=100, help='AP1<->edge link bandwidth (Mbit/s)')
    ap.add_argument('--delay-edge', default='2ms', help='AP1<->edge delay')
    ap.add_argument('--loss-edge', type=float, default=0.05, help='AP1<->edge loss (%)')

    ap.add_argument('--configure-qos', action='store_true',
                    help='Attach OVS HTB QoS queues on ap1-eth2, ap1-eth3, ap2-eth2')
    return ap.parse_args()

def main():
    setLogLevel('info')
    args = parse_args()
    net = build(args)
    try:
        CLI(net)
    finally:
        net.stop()

if __name__ == '__main__':
    main()
