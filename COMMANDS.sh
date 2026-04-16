#!/bin/bash
# =============================================================================
# SDN PORT MONITOR — COMPLETE STEP-BY-STEP COMMANDS
# Copy-paste these in order. Each section is a separate terminal session.
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# PART 1: ONE-TIME SETUP (run once on your VM)
# ─────────────────────────────────────────────────────────────────────────────

# 1.1 Update system
sudo apt update && sudo apt upgrade -y

# 1.2 Install Mininet (includes OVS)
sudo apt install -y mininet

# 1.3 Verify Mininet works
sudo mn --test pingall
sudo mn --clean

# 1.4 Install extra tools
sudo apt install -y iperf wireshark tshark net-tools git curl

# 1.5 Allow Wireshark for non-root user
sudo usermod -aG wireshark $USER
newgrp wireshark

# 1.6 Install POX
cd ~
git clone https://github.com/noxrepo/pox.git

# 1.7 Clone this project (replace with your actual path)
cd ~
# If from GitHub:
# git clone https://github.com/YOUR_USER/sdn-port-monitor.git
# cd sdn-port-monitor
# If from local files, just cd to the folder:
cd ~/sdn-port-monitor    # or wherever you extracted the project

chmod +x run.sh

# 1.8 Setup (copies controller to POX)
./run.sh setup


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: RUNNING THE PROJECT (open 3 terminals)
# ─────────────────────────────────────────────────────────────────────────────

### ══ TERMINAL 1: Start Controller ══
cd ~/pox
cp ~/sdn-port-monitor/controller/port_monitor.py ext/port_monitor.py
python3 pox.py log.level --DEBUG openflow.of_01 port_monitor
# Keep this running. You'll see logs here.


### ══ TERMINAL 2: Start Mininet ══
cd ~/sdn-port-monitor

# Clean any old state first
sudo mn --clean

# Start topology (interactive CLI)
sudo python3 topology.py

# --- OR run all scenarios automatically ---
sudo python3 topology.py all


### ══ TERMINAL 3: Live Dashboard ══
cd ~/sdn-port-monitor
python3 monitor_dashboard.py


# ─────────────────────────────────────────────────────────────────────────────
# PART 3: SCENARIO COMMANDS (run inside Mininet CLI: mininet>)
# ─────────────────────────────────────────────────────────────────────────────

# === SCENARIO 1: ALLOWED TRAFFIC ===

# 1. Ping from h1 to h6 (should SUCCEED)
mininet> h1 ping -c 4 10.0.0.6

# 2. Ping all hosts
mininet> pingall

# 3. iperf TCP test (should SUCCEED)
mininet> h6 iperf -s &
mininet> h1 iperf -c 10.0.0.6 -t 5
mininet> h6 kill %iperf

# 4. iperf UDP test
mininet> h6 iperf -s -u &
mininet> h1 iperf -c 10.0.0.6 -u -b 1M -t 5
mininet> h6 kill %iperf


# === SCENARIO 2: BLOCKED TRAFFIC ===

# 1. Ping from BLOCKED host h5 (should FAIL - 100% packet loss)
mininet> h5 ping -c 4 10.0.0.1

# 2. Ping to h5 from h1 (should FAIL)
mininet> h1 ping -c 4 -W 2 10.0.0.5

# 3. Try Telnet port 23 (should be BLOCKED by OpenFlow rule)
mininet> h6 nc -l 23 &
mininet> h1 nc -zv -w 2 10.0.0.6 23
mininet> h6 kill %nc

# 4. Try IRC port 6667 (should be BLOCKED)
mininet> h6 nc -l 6667 &
mininet> h1 nc -zv -w 2 10.0.0.6 6667
mininet> h6 kill %nc

# 5. Compare: allowed port 80 (if server were running)
# This would SUCCEED (no block rule for port 80)
mininet> h6 nc -l 80 &
mininet> h1 nc -zv -w 2 10.0.0.6 80
mininet> h6 kill %nc


# === SCENARIO 3: LINK FAILURE ===

# 1. Normal ping before failure
mininet> h1 ping -c 3 10.0.0.6

# 2. Bring down s1-s2 link
mininet> s1 ifconfig s1-eth4 down

# Watch Terminal 1 for: "[!] LINK FAILURE: ... Port X went DOWN"
# Watch Terminal 3 for: Port status → DOWN

# 3. Ping during failure (routes via s1-s3-s2 redundant path)
mininet> h1 ping -c 4 -W 3 10.0.0.6

# 4. Restore the link
mininet> s1 ifconfig s1-eth4 up

# Watch Terminal 1 for: "[+] LINK RESTORED: ..."

# 5. Verify connectivity restored
mininet> h1 ping -c 3 10.0.0.6


# === SCENARIO 4: PORT MONITORING ===

# 1. View flow table on s1
mininet> sh ovs-ofctl dump-flows s1

# 2. View flow tables on all switches
mininet> sh ovs-ofctl dump-flows s2
mininet> sh ovs-ofctl dump-flows s3

# 3. View port stats
mininet> sh ovs-ofctl dump-ports s1

# 4. View event log (JSON format)
mininet> sh tail -20 /tmp/sdn_port_monitor.log

# 5. Watch flows in real-time (from a separate terminal)
# watch -n 2 'sudo ovs-ofctl dump-flows s1'


# ─────────────────────────────────────────────────────────────────────────────
# PART 4: VALIDATION COMMANDS (run from regular terminal, not Mininet CLI)
# ─────────────────────────────────────────────────────────────────────────────

# Check flow tables
sudo ovs-ofctl dump-flows s1
sudo ovs-ofctl dump-flows s2
sudo ovs-ofctl dump-flows s3

# Check port stats
sudo ovs-ofctl dump-ports s1

# Check OVS bridge info
sudo ovs-vsctl show

# Watch controller log
tail -f /tmp/pox_controller.log

# View event log (pretty JSON)
cat /tmp/sdn_port_monitor.log | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        print(f\"{e['timestamp']} | {e['event']:30s} | {e['details']}\")
    except: pass
"

# Capture traffic with tshark
sudo tshark -i s1-eth1 -c 20

# Verify OVS is running
sudo ovs-vsctl list-br


# ─────────────────────────────────────────────────────────────────────────────
# PART 5: WIRESHARK DEMO COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

# Option A: GUI Wireshark (requires desktop VM)
sudo wireshark &
# Select interface: s1-eth1 or s1-eth2
# Apply filter: icmp  (to see pings)
# Apply filter: tcp   (to see iperf)
# Apply filter: openflow  (to see OF messages)

# Option B: tshark (command line)
# Capture pings on s1's port to h1
sudo tshark -i s1-eth1 -f "icmp" -c 20

# Capture OpenFlow messages
sudo tshark -i lo -f "tcp port 6633" -c 50

# Save a capture
sudo tshark -i s1-eth1 -w /tmp/capture.pcap -c 100
# Then open in Wireshark: wireshark /tmp/capture.pcap


# ─────────────────────────────────────────────────────────────────────────────
# PART 6: CLEANUP
# ─────────────────────────────────────────────────────────────────────────────

# In Mininet CLI:
mininet> exit

# Stop POX (in Terminal 1):
# Ctrl+C

# Clean everything:
sudo mn --clean
sudo pkill -f "pox.py"
sudo rm -f /tmp/sdn_port_monitor.log /tmp/pox_controller.log


# ─────────────────────────────────────────────────────────────────────────────
# QUICK REFERENCE: What Each Command Shows
# ─────────────────────────────────────────────────────────────────────────────
#
#  sudo ovs-ofctl dump-flows s1
#    → Shows all OpenFlow rules installed on s1
#    → Look for: priority=65535 (block h5), priority=60000 (block ports)
#
#  sudo ovs-ofctl dump-ports s1
#    → Shows TX/RX bytes and errors per port
#
#  tail -f /tmp/sdn_port_monitor.log
#    → Real-time JSON event stream from controller
#    → Shows: PORT_INIT, PORT_STATUS, PACKET_IN, FLOW_INSTALLED, etc.
#
#  tail -f /tmp/pox_controller.log
#    → Raw POX controller output with DEBUG logs
#
#  pingall (in Mininet CLI)
#    → Tests all-pairs connectivity
#    → h5 should fail to reach others (blocked by ACL)
# =============================================================================
