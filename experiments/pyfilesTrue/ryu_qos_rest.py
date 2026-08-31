#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ryu QoS REST app (OpenFlow 1.3)

Purpose
-------
Expose a tiny REST API so an external orchestrator (TraCI/SUMO) can
POST intersection "busy" metrics. When 'busy' is high, we install a
priority flow that puts UDP:9999 control packets into queue 1 on all
connected OVS AP bridges; when 'busy' falls, we remove that rule.

Endpoints
---------
GET  /health      -> {"status":"ok","priority_enabled":bool}
POST /metrics     -> accept JSON {"busy": <float>, "ns_q": <int?>, "ew_q": <int?>}
                     returns {"status":"ok","busy": <float>,"priority": bool}

Run
---
ryu-manager ryu_qos_rest.py
# if 8080 is busy: ryu-manager --wsapi-port 8081 ryu_qos_rest.py

Notes
-----
* Ensures WSGI is available via _CONTEXTS to avoid KeyError('wsgi').
* Returns JSON *bytes* with charset to avoid WebOb "charset" TypeError.
* Tracks datapaths via OFP state change (MAIN/DEAD) and reinstalls flows
  on reconnects if priority is currently enabled.
* The app does NOT create OVS queues; you attach QoS queues on wired ports
  (apX-ethY) from Mininet CLI. The set_queue action selects queue 1 on
  the egress port that NORMAL forwarding chooses.
"""

import json
from typing import Dict, Optional

from ryu.base import app_manager
from ryu.app.wsgi import WSGIApplication, ControllerBase, route
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
)
from ryu.ofproto import ofproto_v1_3
from webob import Response


APP_KEY   = 'qos_rest_app'
REST_BASE = '/metrics'


def json_response(obj: dict, status: int = 200) -> Response:
    """Return a WebOb Response carrying JSON bytes with charset."""
    body = json.dumps(obj).encode('utf-8')
    return Response(status=status,
                    content_type='application/json; charset=utf-8',
                    body=body)


class QosRestSwitch(app_manager.RyuApp):
    """
    Ryu app that toggles a single high-priority flow:

      match:  eth_type=0x0800, ip_proto=17 (UDP), udp_dst=9999
      action: set_queue:1, OUTPUT:NORMAL

    Priority is globally enabled/disabled based on metrics posted to the REST API.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    # ---- configuration knobs (tweak if you like) ----
    CTRL_UDP_PORT      = 9999
    QOS_EGRESS_PORT    = 4     # ap1-edge dans la topologie experimentale
    COOKIE             = 0xABC
    ENABLE_THRESHOLD   = 8.0   # turn ON when busy >= this
    DISABLE_THRESHOLD  = 3.0   # turn OFF when busy <= this
    NORMAL_FALLBACK    = True  # install a priority=0 NORMAL table-miss for safety

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # REST wiring
        wsgi: WSGIApplication = kwargs['wsgi']
        wsgi.register(QosRestController, {APP_KEY: self})

        # runtime state
        self.datapaths: Dict[int, object] = {}  # dpid -> datapath
        self.priority_enabled: bool = False

        self.logger.info('[Ryu] QoS REST app is up on %s '
                         '(enable>=%.1f, disable<=%.1f; udp=%d)',
                         REST_BASE, self.ENABLE_THRESHOLD,
                         self.DISABLE_THRESHOLD, self.CTRL_UDP_PORT)

    # ---------- OpenFlow helpers ----------

    def _add_flow(self, dp, priority, match, actions,
                  table_id=0, idle_timeout=0, hard_timeout=0, cookie: Optional[int] = None):
        ofp = dp.ofproto
        p   = dp.ofproto_parser
        inst = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = p.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=inst,
            table_id=table_id,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            cookie=self.COOKIE if cookie is None else cookie
        )
        dp.send_msg(mod)

    def _del_flow(self, dp, match, table_id=0):
        ofp = dp.ofproto
        p   = dp.ofproto_parser
        mod = p.OFPFlowMod(
            datapath=dp,
            command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=match,
            table_id=table_id,
            cookie=self.COOKIE,
            cookie_mask=0xFFFFFFFFFFFFFFFF
        )
        dp.send_msg(mod)

    def _ensure_normal_fallback(self, dp):
        """Install a safe low-priority NORMAL rule so we don't blackhole traffic."""
        if not self.NORMAL_FALLBACK:
            return
        ofp = dp.ofproto
        p   = dp.ofproto_parser
        actions = [p.OFPActionOutput(ofp.OFPP_NORMAL)]
        self._add_flow(dp, priority=0, match=p.OFPMatch(), actions=actions)

    def _install_priority_flow(self, dp):
        """Install the UDP:9999 -> queue 1 prioritization rule."""
        ofp = dp.ofproto
        p   = dp.ofproto_parser
        match   = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.CTRL_UDP_PORT)
        # La file est propre au port : une sortie NORMAL ne garantit pas que le
        # contexte de queue sera conserve par tous les datapaths OVS. Le port
        # goulot est donc explicite et stable dans le protocole experimental.
        actions = [p.OFPActionSetQueue(1), p.OFPActionOutput(self.QOS_EGRESS_PORT)]
        self._add_flow(dp, priority=20000, match=match, actions=actions)
        self.logger.info('[Ryu] Installed priority rule on dpid=%s', dp.id)

        # Ne pas appliquer set_queue au retour : la file 1 n'existe que sur le
        # port goulot vers edge. Sur les ports vehicules, set_queue:1 rejetterait
        # les acquittements/reponses et fausserait les mesures.

    def _remove_priority_flow(self, dp):
        """Remove the UDP:9999 prioritization rules."""
        p = dp.ofproto_parser
        self._del_flow(dp, match=p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.CTRL_UDP_PORT))
        self.logger.info('[Ryu] Removed priority rules on dpid=%s', dp.id)

    # ---------- OpenFlow events ----------

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """Track datapath life-cycle so we can (re)push rules."""
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
            self.logger.info('[Ryu] Switch MAIN dpid=%s', dp.id)
        elif ev.state == DEAD_DISPATCHER:
            if dp.id in self.datapaths:
                del self.datapaths[dp.id]
                self.logger.info('[Ryu] Switch DEAD dpid=%s', dp.id)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features(self, ev):
        """Initial setup when a switch connects."""
        dp = ev.msg.datapath
        self._ensure_normal_fallback(dp)
        self.logger.info('[Ryu] FeaturesReply dpid=%s (OpenFlow13 ready)', dp.id)
        # If we were already in priority mode, reinstall now.
        if self.priority_enabled:
            try:
                self._install_priority_flow(dp)
            except Exception as e:
                self.logger.error('[Ryu] Reinstall priority failed on dpid=%s: %s', dp.id, e)

    # ---------- Global toggle API ----------

    def flip_priority(self, enable: bool):
        """Enable/disable priority on all known datapaths."""
        if enable == self.priority_enabled:
            return
        self.priority_enabled = enable
        for dpid, dp in list(self.datapaths.items()):
            try:
                if enable:
                    self._install_priority_flow(dp)
                else:
                    self._remove_priority_flow(dp)
            except Exception as e:
                self.logger.error('[Ryu] Updating dpid=%s failed: %s', dpid, e)


class QosRestController(ControllerBase):
    """WSGI controller exposing /health and /metrics."""
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app: QosRestSwitch = data[APP_KEY]

    @route('qos-health', '/health', methods=['GET'])
    def health(self, req, **kwargs):
        return json_response({
            'status': 'ok',
            'priority_enabled': self.app.priority_enabled
        })

    @route('qos-metrics', REST_BASE, methods=['POST'])
    def metrics(self, req, **kwargs):
        # Accept JSON {"busy": float, "ns_q": int?, "ew_q": int?}
        try:
            if req.content_type and 'application/json' in req.content_type.lower():
                data = req.json  # parsed by WebOb
            else:
                data = json.loads(req.body.decode('utf-8'))
        except Exception:
            return json_response({'error': 'invalid json'}, status=400)

        ns_q = int(data.get('ns_q', 0) or 0)
        ew_q = int(data.get('ew_q', 0) or 0)
        try:
            busy = float(data.get('busy', ns_q + ew_q))
        except Exception:
            busy = 0.0

        # Hysteresis: avoid flapping
        if not self.app.priority_enabled and busy >= self.app.ENABLE_THRESHOLD:
            self.app.flip_priority(True)
        elif self.app.priority_enabled and busy <= self.app.DISABLE_THRESHOLD:
            self.app.flip_priority(False)

        return json_response({
            'status': 'ok',
            'busy': busy,
            'priority': self.app.priority_enabled
        })
