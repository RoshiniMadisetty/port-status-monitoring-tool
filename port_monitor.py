"""
Port Status Monitoring Controller - POX SDN Controller
======================================================
Implements:
 - OpenFlow match-action rules (L2 switching + ACL)
 - packet_in event handling
 - Port status monitoring (port up/down events)
 - Allowed vs Blocked traffic scenarios
 - Normal vs Link-failure scenarios
"""

from pox.core import core
from pox.lib.util import dpidToStr
from pox.lib.addresses import IPAddr, EthAddr
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.recoco import Timer
import time
import json
import os

log = core.getLogger()

# ─── Configuration ────────────────────────────────────────────────────────────

# Ports that are BLOCKED (scenario: blocked traffic)
BLOCKED_PORTS_TCP = [23, 6667]          # Telnet, IRC - always block
BLOCKED_SRC_IP    = "10.0.0.5"         # Host h5 is quarantined

# Allowed scenario ports
ALLOWED_PORTS_TCP = [80, 443, 5001]    # HTTP, HTTPS, iperf

# Port monitoring state
port_stats = {}          # dpid -> { port_no -> { status, tx, rx, errors } }
link_failures = {}       # dpid -> [ port_no ]
flow_table    = {}       # dpid -> [ flow_entry ]

LOG_FILE = "/tmp/sdn_port_monitor.log"

# ─── Utilities ────────────────────────────────────────────────────────────────

def log_event(event_type, details):
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event":     event_type,
        "details":   details
    }
    line = json.dumps(entry)
    log.info(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def port_status_str(status):
    return "UP" if status else "DOWN"

# ─── Main Component ───────────────────────────────────────────────────────────

class PortMonitorController(EventMixin):

    def __init__(self):
        self.listenTo(core.openflow)
        self.mac_to_port = {}        # { dpid: { mac: port } }
        self._timer = Timer(10, self._poll_stats, recurring=True)
        log_event("CONTROLLER_START", {"msg": "Port Status Monitor Controller started"})
        log.info("=== Port Status Monitor Controller Started ===")

    # ── Connection Up ──────────────────────────────────────────────────────────

    def _handle_ConnectionUp(self, event):
        dpid = dpidToStr(event.dpid)
        log.info(f"[+] Switch connected: {dpid}")
        self.mac_to_port[event.dpid] = {}
        port_stats[event.dpid]       = {}
        link_failures[event.dpid]    = []
        flow_table[event.dpid]       = []

        # Initialise port state from features
        for p in event.ofp.ports:
            if p.port_no < of.OFPP_MAX:
                is_up = not (p.state & of.OFPPS_LINK_DOWN)
                port_stats[event.dpid][p.port_no] = {
                    "name":   p.name.decode() if isinstance(p.name, bytes) else p.name,
                    "status": is_up,
                    "tx_bytes": 0, "rx_bytes": 0, "errors": 0
                }
                log_event("PORT_INIT", {
                    "switch": dpid,
                    "port":   p.port_no,
                    "name":   port_stats[event.dpid][p.port_no]["name"],
                    "status": port_status_str(is_up)
                })

        # Install proactive rules
        self._install_base_rules(event)
        log_event("SWITCH_CONNECTED", {"switch": dpid, "ports": len(port_stats[event.dpid])})

    # ── Base OpenFlow Rules (proactive) ───────────────────────────────────────

    def _install_base_rules(self, event):
        """Install static match-action rules on the switch."""
        dpid = dpidToStr(event.dpid)

        # Rule 0: BLOCK quarantined source IP (highest priority)
        msg = of.ofp_flow_mod()
        msg.priority = 65535
        msg.match.dl_type = 0x0800          # IPv4
        msg.match.nw_src  = IPAddr(BLOCKED_SRC_IP)
        msg.actions       = []              # empty = DROP
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 65535, "match": f"ip_src={BLOCKED_SRC_IP}", "action": "DROP"
        })
        log.info(f"  [RULE] BLOCK src IP {BLOCKED_SRC_IP} on {dpid}")

        # Rule 1: BLOCK Telnet (TCP dst 23)
        msg = of.ofp_flow_mod()
        msg.priority = 60000
        msg.match.dl_type  = 0x0800
        msg.match.nw_proto = 6              # TCP
        msg.match.tp_dst   = 23
        msg.actions        = []
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 60000, "match": "tcp_dst=23", "action": "DROP"
        })
        log.info(f"  [RULE] BLOCK Telnet (TCP/23) on {dpid}")

        # Rule 2: BLOCK IRC (TCP dst 6667)
        msg = of.ofp_flow_mod()
        msg.priority = 60000
        msg.match.dl_type  = 0x0800
        msg.match.nw_proto = 6
        msg.match.tp_dst   = 6667
        msg.actions        = []
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 60000, "match": "tcp_dst=6667", "action": "DROP"
        })
        log.info(f"  [RULE] BLOCK IRC (TCP/6667) on {dpid}")

        # Rule 3: ALLOW ARP - flood
        msg = of.ofp_flow_mod()
        msg.priority = 50000
        msg.match.dl_type = 0x0806          # ARP
        msg.actions = [of.ofp_action_output(port=of.OFPP_FLOOD)]
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 50000, "match": "arp", "action": "FLOOD"
        })
        log.info(f"  [RULE] ALLOW ARP flood on {dpid}")

        # Rule 4: ALLOW ICMP (ping)
        msg = of.ofp_flow_mod()
        msg.priority = 40000
        msg.match.dl_type  = 0x0800
        msg.match.nw_proto = 1              # ICMP
        msg.actions        = [of.ofp_action_output(port=of.OFPP_CONTROLLER)]
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 40000, "match": "icmp", "action": "TO_CONTROLLER"
        })
        log.info(f"  [RULE] ALLOW ICMP (to controller for learning) on {dpid}")

        # Rule 5: Send remaining IP to controller for reactive learning
        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.match.dl_type = 0x0800
        msg.actions       = [of.ofp_action_output(port=of.OFPP_CONTROLLER)]
        event.connection.send(msg)
        flow_table[event.dpid].append({
            "priority": 100, "match": "ip", "action": "TO_CONTROLLER"
        })

        log_event("RULES_INSTALLED", {"switch": dpid, "count": len(flow_table[event.dpid])})
        log.info(f"  [+] {len(flow_table[event.dpid])} base rules installed on {dpid}")

    # ── Packet In (reactive learning) ─────────────────────────────────────────

    def _handle_PacketIn(self, event):
        packet  = event.parsed
        dpid    = event.dpid
        in_port = event.port

        if not packet.parsed:
            log.warning("Unparsed packet, dropping")
            return

        src_mac = str(packet.src)
        dst_mac = str(packet.dst)

        # Learn src MAC -> port
        if dpid not in self.mac_to_port:
            self.mac_to_port[dpid] = {}
        self.mac_to_port[dpid][src_mac] = in_port

        log_event("PACKET_IN", {
            "switch":   dpidToStr(dpid),
            "in_port":  in_port,
            "src_mac":  src_mac,
            "dst_mac":  dst_mac,
            "eth_type": hex(packet.type)
        })

        # If we know the destination, install a flow and forward
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]

            # Install reactive flow: src->dst MAC forwarding rule
            msg = of.ofp_flow_mod()
            msg.priority    = 1000
            msg.idle_timeout  = 30
            msg.hard_timeout  = 120
            msg.match.dl_src = EthAddr(src_mac)
            msg.match.dl_dst = EthAddr(dst_mac)
            msg.actions      = [of.ofp_action_output(port=out_port)]
            msg.data         = event.ofp
            event.connection.send(msg)

            log_event("FLOW_INSTALLED", {
                "switch":    dpidToStr(dpid),
                "src_mac":  src_mac,
                "dst_mac":  dst_mac,
                "out_port": out_port,
                "type":     "REACTIVE_L2"
            })
        else:
            # Flood unknown destination
            msg = of.ofp_packet_out()
            msg.data    = event.ofp
            msg.actions = [of.ofp_action_output(port=of.OFPP_FLOOD)]
            msg.in_port = in_port
            event.connection.send(msg)

    # ── Port Status Events ────────────────────────────────────────────────────

    def _handle_PortStatus(self, event):
        dpid    = dpidToStr(event.dpid)
        port_no = event.ofp.desc.port_no
        reason  = event.ofp.reason

        reason_map = {
            of.OFPPR_ADD:    "PORT_ADDED",
            of.OFPPR_DELETE: "PORT_DELETED",
            of.OFPPR_MODIFY: "PORT_MODIFIED"
        }
        reason_str = reason_map.get(reason, "UNKNOWN")

        is_up = not (event.ofp.desc.state & of.OFPPS_LINK_DOWN)
        status_str = port_status_str(is_up)

        if event.dpid in port_stats:
            if port_no in port_stats[event.dpid]:
                port_stats[event.dpid][port_no]["status"] = is_up

            if not is_up:
                if port_no not in link_failures.get(event.dpid, []):
                    link_failures.setdefault(event.dpid, []).append(port_no)
                log.warning(f"[!] LINK FAILURE: Switch {dpid} Port {port_no} went DOWN")
                self._handle_link_failure(event.dpid, port_no)
            else:
                if port_no in link_failures.get(event.dpid, []):
                    link_failures[event.dpid].remove(port_no)
                log.info(f"[+] LINK RESTORED: Switch {dpid} Port {port_no} back UP")
                self._handle_link_restore(event.dpid, port_no)

        log_event("PORT_STATUS", {
            "switch":  dpid,
            "port":    port_no,
            "reason":  reason_str,
            "status":  status_str
        })

    def _handle_link_failure(self, dpid, port_no):
        """React to a link failure: flush affected flows."""
        conn = None
        for c in core.openflow.connections:
            if c.dpid == dpid:
                conn = c
                break
        if not conn:
            return

        # Delete all flows going out of the failed port
        msg = of.ofp_flow_mod()
        msg.command = of.OFPFC_DELETE
        msg.out_port = port_no
        conn.send(msg)

        log_event("LINK_FAILURE_HANDLED", {
            "switch": dpidToStr(dpid),
            "port":   port_no,
            "action": "FLOWS_FLUSHED"
        })
        log.warning(f"  [!] Flushed flows for failed port {port_no} on {dpidToStr(dpid)}")

    def _handle_link_restore(self, dpid, port_no):
        """React to link restore: reinstall base rules."""
        conn = None
        for c in core.openflow.connections:
            if c.dpid == dpid:
                conn = c
                break
        if conn:
            log_event("LINK_RESTORED", {
                "switch": dpidToStr(dpid),
                "port":   port_no,
                "action": "BASE_RULES_REINSTALLED"
            })

    # ── Stats Polling ─────────────────────────────────────────────────────────

    def _poll_stats(self):
        for conn in core.openflow.connections:
            conn.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))

    def _handle_PortStatsReceived(self, event):
        dpid = event.connection.dpid
        for stat in event.stats:
            pno = stat.port_no
            if pno >= of.OFPP_MAX:
                continue
            if dpid not in port_stats:
                port_stats[dpid] = {}
            if pno not in port_stats[dpid]:
                port_stats[dpid][pno] = {"name": str(pno), "status": True,
                                          "tx_bytes": 0, "rx_bytes": 0, "errors": 0}
            port_stats[dpid][pno].update({
                "tx_bytes": stat.tx_bytes,
                "rx_bytes": stat.rx_bytes,
                "errors":   stat.tx_errors + stat.rx_errors
            })

        # Print a summary every poll
        dpid_str = dpidToStr(dpid)
        log.info(f"--- Port Stats [{dpid_str}] ---")
        for pno, info in sorted(port_stats.get(dpid, {}).items()):
            log.info(
                f"  Port {pno:2d} ({info.get('name','?'):8s}) | "
                f"Status: {port_status_str(info['status']):4s} | "
                f"TX: {info['tx_bytes']:>10} B | RX: {info['rx_bytes']:>10} B | "
                f"Errors: {info['errors']}"
            )
        log_event("STATS_POLL", {"switch": dpid_str, "ports": len(port_stats.get(dpid, {}))})

    # ── Connection Down ────────────────────────────────────────────────────────

    def _handle_ConnectionDown(self, event):
        dpid = dpidToStr(event.dpid)
        log.warning(f"[-] Switch disconnected: {dpid}")
        log_event("SWITCH_DISCONNECTED", {"switch": dpid})


# ─── Launch ───────────────────────────────────────────────────────────────────

def launch():
    core.registerNew(PortMonitorController)
    log.info("Port Status Monitor Controller registered.")
