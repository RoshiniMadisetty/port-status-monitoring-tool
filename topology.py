#!/usr/bin/env python3
"""
SDN Port Monitoring - Custom Mininet Topology
==============================================

Topology:
                        ┌─────────────────────────┐
                        │     POX Controller       │
                        │    (127.0.0.1:6633)      │
                        └────────────┬────────────┘
                                     │ OpenFlow
              ┌──────────────────────┼──────────────────────┐
              │                      │                       │
           [s1]                    [s2]                   [s3]
         /   |   \                /    \                  /   \
       h1   h2   h3             h4    h5(blocked)      h6    h7
  10.0.0.1 .2  .3           10.0.0.4  10.0.0.5     10.0.0.6  10.0.0.7

  s1 -- s2 -- s3  (linear inter-switch links)
  h5 is quarantined (blocked by ACL rule)
"""

from mininet.net    import Mininet
from mininet.node   import Controller, RemoteController, OVSKernelSwitch
from mininet.cli    import CLI
from mininet.log    import setLogLevel, info
from mininet.link   import TCLink
from mininet.topo   import Topo
import time
import subprocess
import sys

# ─── Custom Topology ─────────────────────────────────────────────────────────

class PortMonitorTopo(Topo):
    """Three-switch topology with 7 hosts."""

    def build(self):
        # Switches
        s1 = self.addSwitch('s1', protocols='OpenFlow10')
        s2 = self.addSwitch('s2', protocols='OpenFlow10')
        s3 = self.addSwitch('s3', protocols='OpenFlow10')

        # Hosts - assign IPs and MACs explicitly
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')
        h5 = self.addHost('h5', ip='10.0.0.5/24', mac='00:00:00:00:00:05')  # BLOCKED
        h6 = self.addHost('h6', ip='10.0.0.6/24', mac='00:00:00:00:00:06')
        h7 = self.addHost('h7', ip='10.0.0.7/24', mac='00:00:00:00:00:07')

        # Host links (bandwidth limited to 10Mbps for demo)
        self.addLink(h1, s1, bw=10, delay='2ms')
        self.addLink(h2, s1, bw=10, delay='2ms')
        self.addLink(h3, s1, bw=10, delay='2ms')
        self.addLink(h4, s2, bw=10, delay='2ms')
        self.addLink(h5, s2, bw=10, delay='2ms')   # quarantined host
        self.addLink(h6, s3, bw=10, delay='2ms')
        self.addLink(h7, s3, bw=10, delay='2ms')

        # Inter-switch links (higher bandwidth)
        self.addLink(s1, s2, bw=100, delay='5ms')
        self.addLink(s2, s3, bw=100, delay='5ms')
        self.addLink(s1, s3, bw=100, delay='5ms')  # redundant link for failure demo


# ─── Scenario Runners ─────────────────────────────────────────────────────────

def scenario_allowed_traffic(net):
    """Scenario 1: Allowed traffic (HTTP, ICMP, iperf)."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO 1: ALLOWED TRAFFIC\n")
    info("="*60 + "\n")

    h1 = net.get('h1')
    h6 = net.get('h6')

    info("\n[1.1] Ping test h1 -> h6 (SHOULD SUCCEED)\n")
    result = h1.cmd('ping -c 4 10.0.0.6')
    info(result)

    info("\n[1.2] iperf test h1 -> h6 (SHOULD SUCCEED)\n")
    info("  Starting iperf server on h6...\n")
    h6.cmd('iperf -s -D')
    time.sleep(1)
    result = h1.cmd('iperf -c 10.0.0.6 -t 5')
    info(result)
    h6.cmd('kill %iperf 2>/dev/null; pkill iperf 2>/dev/null')

    info("\n[1.3] iperf UDP test h1 -> h6\n")
    h6.cmd('iperf -s -u -D')
    time.sleep(1)
    result = h1.cmd('iperf -c 10.0.0.6 -u -b 1M -t 5')
    info(result)
    h6.cmd('kill %iperf 2>/dev/null; pkill iperf 2>/dev/null')

def scenario_blocked_traffic(net):
    """Scenario 2: Blocked traffic (quarantined host, blocked ports)."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO 2: BLOCKED TRAFFIC\n")
    info("="*60 + "\n")

    h1 = net.get('h1')
    h5 = net.get('h5')
    h6 = net.get('h6')

    info("\n[2.1] Ping from BLOCKED host h5 -> h1 (SHOULD FAIL)\n")
    result = h5.cmd('ping -c 4 -W 2 10.0.0.1')
    info(result)

    info("\n[2.2] Ping from h1 -> h5 (SHOULD FAIL - h5 IP is blocked)\n")
    result = h1.cmd('ping -c 4 -W 2 10.0.0.5')
    info(result)

    info("\n[2.3] Telnet attempt h1 -> h6 port 23 (SHOULD BE BLOCKED)\n")
    h6.cmd('nc -l 23 &')
    time.sleep(0.5)
    result = h1.cmd('nc -zv -w 2 10.0.0.6 23 2>&1')
    info(f"  Result: {result.strip()}\n")
    h6.cmd('kill %nc 2>/dev/null')

    info("\n[2.4] IRC port 6667 attempt (SHOULD BE BLOCKED)\n")
    h6.cmd('nc -l 6667 &')
    time.sleep(0.5)
    result = h1.cmd('nc -zv -w 2 10.0.0.6 6667 2>&1')
    info(f"  Result: {result.strip()}\n")
    h6.cmd('kill %nc 2>/dev/null')

def scenario_link_failure(net):
    """Scenario 3: Link failure and recovery."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO 3: LINK FAILURE & RECOVERY\n")
    info("="*60 + "\n")

    h1  = net.get('h1')
    h6  = net.get('h6')
    s1  = net.get('s1')
    s2  = net.get('s2')

    info("\n[3.1] Normal ping h1 -> h6 BEFORE failure\n")
    result = h1.cmd('ping -c 3 10.0.0.6')
    info(result)

    info("\n[3.2] Bringing down s1-s2 link (simulating failure)...\n")
    s1.cmd('ifconfig s1-eth4 down')  # s1-s2 link
    time.sleep(2)

    info("\n[3.3] Ping h1 -> h6 DURING failure (uses s1-s3-s2 path)\n")
    result = h1.cmd('ping -c 4 -W 2 10.0.0.6')
    info(result)

    info("\n[3.4] Restoring s1-s2 link...\n")
    s1.cmd('ifconfig s1-eth4 up')
    time.sleep(3)

    info("\n[3.5] Ping h1 -> h6 AFTER recovery\n")
    result = h1.cmd('ping -c 3 10.0.0.6')
    info(result)

def scenario_port_monitoring(net):
    """Scenario 4: Demonstrate port status monitoring output."""
    info("\n" + "="*60 + "\n")
    info("SCENARIO 4: PORT STATUS MONITORING\n")
    info("="*60 + "\n")

    info("\n[4.1] Checking log for port events...\n")
    try:
        with open('/tmp/sdn_port_monitor.log', 'r') as f:
            lines = f.readlines()
        last = lines[-30:] if len(lines) > 30 else lines
        for line in last:
            info(f"  {line.rstrip()}\n")
    except FileNotFoundError:
        info("  Log not found yet - start controller first\n")

    info("\n[4.2] Checking OVS flow tables...\n")
    for sw in ['s1', 's2', 's3']:
        info(f"\n  --- {sw} flow table ---\n")
        result = subprocess.getoutput(f'ovs-ofctl dump-flows {sw}')
        info(result + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run():
    setLogLevel('info')

    topo = PortMonitorTopo()
    net  = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=False
    )

    info("\n=== Starting SDN Port Monitor Network ===\n")
    net.start()

    # Wait for controller to connect
    info("Waiting for controller connection (5s)...\n")
    time.sleep(5)

    # Run scenarios based on argument
    if len(sys.argv) > 1:
        scenario = sys.argv[1]
        if scenario == 'allowed':
            scenario_allowed_traffic(net)
        elif scenario == 'blocked':
            scenario_blocked_traffic(net)
        elif scenario == 'failure':
            scenario_link_failure(net)
        elif scenario == 'monitor':
            scenario_port_monitoring(net)
        elif scenario == 'all':
            scenario_allowed_traffic(net)
            scenario_blocked_traffic(net)
            scenario_link_failure(net)
            scenario_port_monitoring(net)
        else:
            info(f"Unknown scenario: {scenario}\n")
    else:
        info("\nNo scenario specified - opening CLI\n")
        info("Run scenarios manually:\n")
        info("  sudo python3 topology.py all\n")
        info("  sudo python3 topology.py allowed\n")
        info("  sudo python3 topology.py blocked\n")
        info("  sudo python3 topology.py failure\n")

    info("\n=== Opening Mininet CLI ===\n")
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
