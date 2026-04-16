# SDN Port Status Monitoring Tool
### Mininet + POX Controller | OpenFlow 1.0 | Python 3

> A complete Software-Defined Networking project demonstrating **port status monitoring**, **explicit OpenFlow match-action rules**, **packet_in event handling**, and **multi-scenario validation** (allowed vs blocked traffic, normal vs link failure).

---

## 📋 Table of Contents
- [Architecture & Topology](#architecture--topology)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Project](#running-the-project)
- [Scenarios](#scenarios)
- [Testing & Validation](#testing--validation)
- [File Structure](#file-structure)
- [OpenFlow Rules Explained](#openflow-rules-explained)

---

## Architecture & Topology

```
                    ┌─────────────────────────┐
                    │     POX Controller       │
                    │  (OpenFlow 1.0 / TCP 6633)│
                    └────────────┬────────────┘
                                 │ OpenFlow Channel
          ┌──────────────────────┼──────────────────────┐
          │                      │                       │
       ┌──┴──┐               ┌───┴─┐               ┌────┴┐
       │ s1  │───────────────│ s2  │───────────────│ s3  │
       └─┬─┬─┘               └──┬──┘               └──┬──┘
         │ │ │                  │ │                    │ │
        h1 h2 h3               h4 h5*               h6 h7
   10.0.0.1 .2 .3         .4     .5*           .6     .7

  * h5 is QUARANTINED — all traffic from 10.0.0.5 is BLOCKED by ACL

  Inter-switch links:
    s1 ─── s2  (primary path)
    s2 ─── s3  (primary path)
    s1 ─── s3  (redundant link for failover demo)
```

### Component Roles

| Component | Role |
|---|---|
| `s1, s2, s3` | OVS OpenFlow switches |
| `h1–h4, h6–h7` | Normal hosts (allowed traffic) |
| `h5` | Quarantined host (all traffic blocked) |
| POX Controller | Handles packet_in, installs flow rules, monitors port events |

---

## Features

- ✅ **Custom Mininet topology** — 3 switches, 7 hosts, redundant inter-switch links
- ✅ **POX/RYU-style controller** — written for POX OpenFlow controller
- ✅ **Proactive OpenFlow rules** — installed at switch connect time (ACL, ARP, ICMP)
- ✅ **Reactive MAC learning** — L2 forwarding rules installed dynamically on packet_in
- ✅ **Port status monitoring** — handles PortStatus events (link up/down/add/delete)
- ✅ **Link failure handling** — auto-flushes stale flows on port failure
- ✅ **JSON event log** — all events written to `/tmp/sdn_port_monitor.log`
- ✅ **Live dashboard** — terminal UI showing port states, flow counts, recent events
- ✅ **4 demo scenarios** — allowed traffic, blocked traffic, link failure, port monitoring

---

## Prerequisites

- Ubuntu 20.04/22.04 VM (recommended: 2 CPU, 2GB RAM)
- Python 3.8+
- Mininet
- Open vSwitch (OVS)
- POX controller
- Optional: Wireshark, iperf

---

## Installation

### Step 1 — Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### Step 2 — Install Mininet
```bash
sudo apt install -y mininet
# Verify
sudo mn --test pingall
sudo mn --clean
```

### Step 3 — Install Open vSwitch
```bash
sudo apt install -y openvswitch-switch openvswitch-common
sudo systemctl start openvswitch-switch
sudo systemctl enable openvswitch-switch
# Verify
ovs-vsctl show
```

### Step 4 — Install POX
```bash
cd ~
git clone https://github.com/noxrepo/pox.git
```

### Step 5 — Clone This Project
```bash
git clone https://github.com/YOUR_USERNAME/sdn-port-monitor.git
cd sdn-port-monitor
chmod +x run.sh
```

### Step 6 — Run Setup
```bash
./run.sh setup
```

This copies the controller into the POX `ext/` directory.

### Step 7 — Install Optional Tools
```bash
sudo apt install -y iperf wireshark tshark net-tools
# Allow non-root Wireshark capture
sudo usermod -aG wireshark $USER
newgrp wireshark
```

---

## Running the Project

You will use **3 terminals** for the full demo.

---

### Terminal 1 — Start the Controller

```bash
cd ~/pox
python3 pox.py log.level --DEBUG openflow.of_01 port_monitor
```

Expected output:
```
INFO:port_monitor:=== Port Status Monitor Controller Started ===
INFO:openflow.of_01:Listening on 0.0.0.0:6633
```

---

### Terminal 2 — Start Mininet Topology

```bash
cd ~/sdn-port-monitor
sudo python3 topology.py
```

Or run all scenarios automatically:
```bash
sudo python3 topology.py all
```

Expected output:
```
=== Starting SDN Port Monitor Network ===
Waiting for controller connection (5s)...
*** Adding controller
*** Adding hosts: h1 h2 h3 h4 h5 h6 h7
*** Adding switches: s1 s2 s3
*** Starting network
mininet>
```

---

### Terminal 3 — Live Dashboard

```bash
cd ~/sdn-port-monitor
python3 monitor_dashboard.py
```

---

## Scenarios

### Scenario 1 — Allowed Traffic ✅

Tests that normal traffic flows correctly.

```bash
# In Mininet CLI or:
sudo python3 topology.py allowed
```

**What happens:**
1. `h1 ping h6` — ICMP is allowed, succeeds
2. `h1 iperf h6` — TCP on port 5001 is allowed
3. `h1 iperf -u h6` — UDP traffic allowed

**Manual test in Mininet CLI:**
```
mininet> h1 ping -c 4 h6
mininet> h6 iperf -s &
mininet> h1 iperf -c 10.0.0.6 -t 5
mininet> h6 kill %iperf
```

**Expected:** Pings succeed (~2ms RTT), iperf shows ~9.xx Mbits/sec

---

### Scenario 2 — Blocked Traffic 🚫

Tests that ACL rules block quarantined host and forbidden ports.

```bash
sudo python3 topology.py blocked
```

**What is blocked and why:**

| Test | Rule | Expected |
|---|---|---|
| h5 ping h1 | src IP 10.0.0.5 blocked (priority 65535) | FAIL (100% packet loss) |
| h1 ping h5 | Replies from h5 blocked | FAIL |
| TCP port 23 (Telnet) | Priority 60000 DROP rule | Connection refused/timeout |
| TCP port 6667 (IRC) | Priority 60000 DROP rule | Connection refused/timeout |

**Manual test:**
```
mininet> h5 ping -c 4 h1
# Expected: 100% packet loss

mininet> h6 nc -l 23 &
mininet> h1 nc -zv -w 2 10.0.0.6 23
# Expected: connection timeout
```

---

### Scenario 3 — Link Failure & Recovery 🔌

Demonstrates port status monitoring when a link goes down.

```bash
sudo python3 topology.py failure
```

**What happens:**
1. Normal ping h1→h6 succeeds via s1→s2→s3
2. s1-s2 link is brought DOWN (`ifconfig s1-eth4 down`)
3. Controller receives `PortStatus` event, logs `LINK_FAILURE`, flushes stale flows
4. Traffic reroutes via redundant s1→s3 path
5. Link is restored, controller logs `LINK_RESTORED`

**Manual test:**
```
mininet> h1 ping -c 3 h6
# Success - normal path

mininet> s1 ifconfig s1-eth4 down
# Controller logs: LINK FAILURE on port

mininet> h1 ping -c 4 h6
# Should still work via alternate path

mininet> s1 ifconfig s1-eth4 up
# Controller logs: LINK RESTORED
```

**What to observe in Terminal 1 (controller):**
```
WARNING:port_monitor:[!] LINK FAILURE: Switch 00-00-00... Port X went DOWN
WARNING:port_monitor:  [!] Flushed flows for failed port X
INFO:port_monitor:[+] LINK RESTORED: Switch 00-00-00... Port X back UP
```

---

### Scenario 4 — Port Status Monitoring 📊

View the JSON event log and OVS flow tables.

```bash
sudo python3 topology.py monitor
```

**Manual inspection:**
```bash
# View event log
cat /tmp/sdn_port_monitor.log | python3 -m json.tool | head -80

# View flow table on s1
sudo ovs-ofctl dump-flows s1

# View port statistics
sudo ovs-ofctl dump-ports s1

# Watch flows in real-time
watch -n 2 'sudo ovs-ofctl dump-flows s1'
```

---

## Testing & Validation

### Using Wireshark

```bash
# Capture on s1-h1 interface (from VM host)
sudo wireshark -i s1-eth1 &

# Or use tshark (CLI):
sudo tshark -i s1-eth1 -f "icmp" -c 20
```

To capture in Mininet directly:
```
mininet> h1 tcpdump -i h1-eth0 -w /tmp/h1_capture.pcap &
mininet> h1 ping -c 5 h6
mininet> h1 kill %tcpdump
```

Then open `/tmp/h1_capture.pcap` in Wireshark.

### Using iperf

```bash
# TCP bandwidth test
mininet> h6 iperf -s &
mininet> h1 iperf -c 10.0.0.6 -t 10
mininet> h6 kill %iperf

# UDP test
mininet> h6 iperf -s -u &
mininet> h1 iperf -c 10.0.0.6 -u -b 5M -t 10
```

### Quick Validation Commands

```bash
# Test full mesh connectivity (runs pingall)
mininet> pingall

# Show all flows on all switches
./run.sh flows

# Show port statistics
./run.sh ports

# View event log
./run.sh log

# Check controller log
tail -f /tmp/pox_controller.log
```

---

## File Structure

```
sdn-port-monitor/
├── controller/
│   └── port_monitor.py       # POX controller (main logic)
├── topology.py                # Mininet custom topology + scenarios
├── monitor_dashboard.py       # Live terminal dashboard
├── run.sh                     # Convenience run script
└── README.md                  # This file
```

---

## OpenFlow Rules Explained

Rules are installed by priority (higher = matched first):

| Priority | Match | Action | Purpose |
|---|---|---|---|
| 65535 | ip_src = 10.0.0.5 | DROP | Block quarantined h5 |
| 60000 | tcp_dst = 23 | DROP | Block Telnet |
| 60000 | tcp_dst = 6667 | DROP | Block IRC |
| 50000 | arp | FLOOD | Allow ARP (needed for MAC resolution) |
| 40000 | icmp | TO_CONTROLLER | ICMP to controller for learning |
| 1000  | dl_src + dl_dst | OUTPUT:port | Reactive L2 forwarding rules |
| 100   | ip | TO_CONTROLLER | Unknown IP to controller |

Reactive rules (priority 1000) are installed dynamically when the controller learns a MAC address from a `packet_in` event. They have:
- `idle_timeout = 30s` — removed if no traffic for 30s
- `hard_timeout = 120s` — removed after 2 minutes regardless

---

## Common Issues

| Problem | Fix |
|---|---|
| `mn: command not found` | `sudo apt install mininet` |
| Controller not connecting | Check port 6633 is free: `sudo ss -tlnp | grep 6633` |
| OVS not running | `sudo systemctl start openvswitch-switch` |
| `RTNETLINK answers: Operation not permitted` | Run topology with `sudo` |
| Mininet state dirty | `sudo mn --clean` |



