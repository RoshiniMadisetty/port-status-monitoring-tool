#  SDN Port Monitoring & Dynamic Blocking (POX + Mininet)

## 📌 Overview

This project demonstrates a **Software Defined Networking (SDN)** system using the POX controller and Mininet. It showcases centralized control of network behavior through dynamic flow rule installation, traffic monitoring, and policy-based traffic blocking.

The system implements a learning switch mechanism, monitors network events, enforces security policies, and adapts to topology changes such as link failures.

---

## Network Topology

* **Switches:** s1, s2
* **Hosts:** h1, h2, h3, h4

```
h1 ----\
        s1 -------- s2 ---- h3
h2 ----/              \---- h4
```

* h1, h2 are connected to **s1**
* h3, h4 are connected to **s2**
* s1 and s2 are interconnected

This topology enables inter-switch communication, traffic control, and failure simulation.

---

## ⚙️ Technologies Used

* Python
* POX Controller
* Mininet
* Open vSwitch (OVS)
* Wireshark / Tshark
* iperf

---

## 🚀 Setup Instructions

### 🔹 1. Start Controller

```bash
cd ~/pox
cp ~/sdn-port-monitor/controller.py ext/port_monitor.py
python3 pox.py log.level --DEBUG openflow.of_01 port_monitor
```

---

### 🔹 2. Start Mininet

```bash
cd ~/sdn-port-monitor
sudo mn --clean
sudo python3 topology.py
```

---

## 🔁 Control Flow

When a packet arrives at a switch without a matching flow rule, the switch sends it to the controller as a **packet_in event**.

The controller:

* Analyzes the packet
* Applies policy logic (allow/block)
* Installs a flow rule using a **flow_mod message**

Once installed, future packets are handled directly by the switch. This is called **reactive flow installation**.

---

## 🔒 Traffic Control Policy

The controller enforces a policy using OpenFlow match-action rules:

* **Blocked Traffic:**
  h2 (10.0.0.2) → h3 (10.0.0.3)

* **Allowed Traffic:**
  All other host communications

The blocking is implemented by detecting this flow in the controller and dropping the packet without installing a forwarding rule.

Notes:

* The rule is **unidirectional** (h3 → h2 is allowed)
* Only **IPv4 traffic** is blocked
* ARP packets are unaffected

---

## 🧪 Testing Commands (Mininet CLI)

### 🔹 Verify Network

```bash
net
pingall
```

---

### 🔹 Allowed Traffic

```bash
h1 ping h4
```

Expected: Successful communication

---

### 🔹 Blocked Traffic

```bash
h2 ping h3
```

Expected: 100% packet loss

---

## ⚡ Throughput Validation (iperf)

### Start Server

```bash
h4 iperf -s &
```

### Run Client

```bash
h1 iperf -c 10.0.0.4
```

### Observations:

* Allowed traffic → Normal throughput (~9–10 Mbps)
* Blocked traffic (h2 → h3) → Connection failure / 0 throughput

This confirms correct enforcement of flow rules.

---

## 📡 Packet Analysis (Wireshark / Tshark)

Capture packets using:

```bash
sudo tshark -i s1-eth1
```

### Observations:

* Allowed traffic → ICMP request and reply visible
* Blocked traffic → Only ICMP request, no reply

This verifies packet-level behavior of the controller.

---

## 🔄 Link Failure Simulation

```bash
link s1 s2 down
h1 ping h4   # should fail

link s1 s2 up
h1 ping h4   # should recover
```

The controller detects topology changes and the network adapts accordingly.

---

## 📊 Flow Table & Statistics

```bash
sudo ovs-ofctl dump-flows s1
sudo ovs-ofctl dump-ports s1
```

Used to inspect installed flow rules and port statistics.

---

## 📁 Logs

Log file location:

```bash
/tmp/sdn_port_monitor.log
```

View logs:

```bash
cat /tmp/sdn_port_monitor.log
```

Example:

```json
{"timestamp": "...", "event": "SWITCH_CONNECTED", "details": "s1"}
{"timestamp": "...", "event": "PACKET_IN", "details": "h1 -> h4"}
{"timestamp": "...", "event": "FLOW_INSTALLED", "details": "h1->h4"}
{"timestamp": "...", "event": "BLOCKED", "details": "10.0.0.2 -> 10.0.0.3"}
```

---

## 📌 Features Implemented

* Learning switch using OpenFlow
* MAC-to-port mapping
* Reactive flow installation
* Policy-based traffic blocking
* JSON-based event logging
* Link failure simulation and recovery
* Flow table inspection using OVS
* Packet-level analysis using Wireshark
* Throughput testing using iperf

---

## 💡 Key Concept

The controller acts as the central intelligence of the network by:

* Making forwarding decisions
* Enforcing security policies
* Monitoring network state
* Dynamically adapting to changes

---

## 🧾 Viva Explanation (Short)

> This project demonstrates an SDN-based system where a POX controller dynamically installs flow rules, monitors network activity, blocks specific traffic using policy-based control, and handles link failures. The system is validated using Wireshark for packet analysis and iperf for performance testing.

---

## 👩‍💻 Author

Parnika

---
