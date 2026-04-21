from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.packet import ethernet, ipv4

import json
from datetime import datetime

log = core.getLogger()

# MAC learning table
mac_to_port = {}

LOG_FILE = "/tmp/sdn_port_monitor.log"


# 🔹 Logging function
def log_event(event, details):
    entry = {
        "timestamp": str(datetime.now()),
        "event": event,
        "details": details
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# 🔹 When switch connects
def _handle_ConnectionUp(event):
    dpid = dpid_to_str(event.dpid)
    log.info("Switch %s connected", dpid)
    log_event("SWITCH_CONNECTED", f"{dpid}")


# 🔹 Packet handling (Learning switch + logging)
def _handle_PacketIn(event):
    packet = event.parsed
    dpid = dpid_to_str(event.connection.dpid)
    in_port = event.port

    if not packet.parsed:
        return

    mac_to_port.setdefault(dpid, {})

    # Learn MAC
    mac_to_port[dpid][packet.src] = in_port

    # Log packet event
    log_event("PACKET_IN", f"{packet.src} -> {packet.dst} on {dpid}")

    # 🔥 Example BLOCK rule (block h2 → h3 traffic)
    if packet.find('ipv4'):
        ip = packet.find('ipv4')
        if ip.srcip == "10.0.0.2" and ip.dstip == "10.0.0.3":
            log.info("Blocking traffic from h2 to h3")
            log_event("BLOCKED", "10.0.0.2 -> 10.0.0.3")

            return  # Drop packet

    # If destination known → install flow
    if packet.dst in mac_to_port[dpid]:
        out_port = mac_to_port[dpid][packet.dst]

        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet, in_port)
        msg.actions.append(of.ofp_action_output(port=out_port))
        event.connection.send(msg)

        log_event("FLOW_INSTALLED", f"{packet.src}->{packet.dst} via {dpid}")

    else:
        # Flood
        msg = of.ofp_packet_out()
        msg.data = event.ofp
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        msg.in_port = in_port
        event.connection.send(msg)


# 🔹 Launch function
def launch():
    log.info("Starting Port Monitor Controller...")
    open(LOG_FILE, "w").close()  # Clear old logs

    core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp)
    core.openflow.addListenerByName("PacketIn", _handle_PacketIn)

port monitor.py
