#!/usr/bin/env python3
"""
SDN Port Status Monitor Dashboard
===================================
Real-time terminal dashboard that reads from the controller's log
and shows live port status for all switches.

Usage: python3 monitor_dashboard.py
"""

import json
import time
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

LOG_FILE = "/tmp/sdn_port_monitor.log"

# ANSI color codes
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"

def read_log_events(n=200):
    """Read last n events from log."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        events = []
        for line in lines[-n:]:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
        return events
    except Exception:
        return []

def get_ovs_flows(switch):
    """Get flow entries from a switch."""
    try:
        result = subprocess.run(
            ['ovs-ofctl', 'dump-flows', switch],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout
    except Exception:
        return "N/A"

def get_ovs_ports(switch):
    """Get port status from OVS."""
    try:
        result = subprocess.run(
            ['ovs-ofctl', 'dump-ports', switch],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout
    except Exception:
        return "N/A"

def parse_port_status_from_events(events):
    """Build a port status dict from log events."""
    port_state = defaultdict(dict)
    for ev in events:
        if ev.get('event') == 'PORT_INIT':
            d = ev['details']
            port_state[d['switch']][d['port']] = {
                'name':   d.get('name', '?'),
                'status': d.get('status', 'UP')
            }
        elif ev.get('event') == 'PORT_STATUS':
            d = ev['details']
            sw, port = d['switch'], d['port']
            if port not in port_state[sw]:
                port_state[sw][port] = {'name': str(port), 'status': 'UP'}
            port_state[sw][port]['status'] = d.get('status', 'UP')
    return port_state

def parse_flows_from_events(events):
    """Get recent flow install events."""
    flows = []
    for ev in reversed(events):
        if ev.get('event') in ('FLOW_INSTALLED', 'RULES_INSTALLED'):
            flows.append(ev)
        if len(flows) >= 10:
            break
    return flows

def parse_recent_events(events, n=15):
    """Get last n significant events."""
    significant = [
        'PORT_STATUS', 'LINK_FAILURE_HANDLED', 'LINK_RESTORED',
        'PACKET_IN', 'FLOW_INSTALLED', 'SWITCH_CONNECTED', 'SWITCH_DISCONNECTED'
    ]
    result = [e for e in events if e.get('event') in significant]
    return result[-n:]

def status_color(status):
    if status == 'UP':
        return f"{GREEN}{BOLD}UP  {RESET}"
    else:
        return f"{RED}{BOLD}DOWN{RESET}"

def draw_dashboard(events):
    """Render the terminal dashboard."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    port_state = parse_port_status_from_events(events)
    recent_ev  = parse_recent_events(events)

    print(CLEAR, end='')
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║         SDN PORT STATUS MONITORING DASHBOARD             ║{RESET}")
    print(f"{BOLD}{CYAN}║                    {now}                 ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}")

    # ── Topology Diagram ──────────────────────────────────────────────────────
    print(f"\n{BOLD}{YELLOW}  TOPOLOGY:{RESET}")
    print(f"""
  {CYAN}h1 h2 h3{RESET}        {CYAN}h4 h5(blocked){RESET}     {CYAN}h6 h7{RESET}
    \\ | /               \\ /                \\ /
    {BOLD}[s1]{RESET}────────────{BOLD}[s2]{RESET}────────────{BOLD}[s3]{RESET}
      \\__________________________/
             (redundant link)
""")

    # ── Port Status Per Switch ────────────────────────────────────────────────
    print(f"{BOLD}{YELLOW}  PORT STATUS:{RESET}")
    print(f"  {'Switch':<10} {'Port':<6} {'Name':<12} {'Status':<10}")
    print(f"  {'─'*10} {'─'*6} {'─'*12} {'─'*10}")

    if port_state:
        for sw in sorted(port_state.keys()):
            for port in sorted(port_state[sw].keys()):
                info   = port_state[sw][port]
                status = info.get('status', 'UP')
                print(f"  {CYAN}{sw:<10}{RESET} {port:<6} {info.get('name','?'):<12} {status_color(status)}")
    else:
        print(f"  {YELLOW}Waiting for controller data...{RESET}")

    # ── OVS Flow Counts ───────────────────────────────────────────────────────
    print(f"\n{BOLD}{YELLOW}  OVS FLOW TABLE SUMMARY:{RESET}")
    for sw in ['s1', 's2', 's3']:
        try:
            r = subprocess.run(['ovs-ofctl', 'dump-flows', sw],
                               capture_output=True, text=True, timeout=2)
            count = r.stdout.count('\ncookie=')
            print(f"  {CYAN}{sw}{RESET}: {count} flows installed")
        except Exception:
            print(f"  {sw}: {YELLOW}N/A (switch not running?){RESET}")

    # ── Recent Events ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}{YELLOW}  RECENT EVENTS:{RESET}")
    print(f"  {'Time':<20} {'Event':<25} {'Details'}")
    print(f"  {'─'*20} {'─'*25} {'─'*30}")

    for ev in recent_ev:
        ts      = ev.get('timestamp', '')[-8:]  # HH:MM:SS
        etype   = ev.get('event', '')
        details = str(ev.get('details', ''))[:50]

        if 'FAILURE' in etype or 'DOWN' in details:
            color = RED
        elif 'RESTORED' in etype or 'UP' in details or 'CONNECTED' in etype:
            color = GREEN
        elif 'BLOCK' in details:
            color = YELLOW
        else:
            color = RESET

        print(f"  {ts:<20} {color}{etype:<25}{RESET} {details}")

    # ── ACL Rules ─────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{YELLOW}  ACTIVE ACL RULES:{RESET}")
    print(f"  {RED}✗ BLOCK{RESET} src IP 10.0.0.5 (h5 quarantined)   [priority 65535]")
    print(f"  {RED}✗ BLOCK{RESET} TCP dst port 23  (Telnet)           [priority 60000]")
    print(f"  {RED}✗ BLOCK{RESET} TCP dst port 6667 (IRC)             [priority 60000]")
    print(f"  {GREEN}✓ ALLOW{RESET} ARP (flood)                         [priority 50000]")
    print(f"  {GREEN}✓ ALLOW{RESET} ICMP                                [priority 40000]")
    print(f"  {GREEN}✓ ALLOW{RESET} All other IP (reactive L2 learning) [priority 1000]")

    print(f"\n  {BOLD}Log:{RESET} {LOG_FILE}   |   Refresh: 3s   |   Ctrl+C to quit")

def main():
    print(f"{YELLOW}Starting SDN Port Monitor Dashboard...{RESET}")
    print(f"Reading from: {LOG_FILE}")
    if not os.path.exists(LOG_FILE):
        print(f"{YELLOW}Waiting for controller to create log file...{RESET}")

    try:
        while True:
            events = read_log_events(500)
            draw_dashboard(events)
            time.sleep(3)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Dashboard stopped.{RESET}")

if __name__ == '__main__':
    main()
