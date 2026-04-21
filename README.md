# SDN Port Monitoring & Dynamic Blocking (POX + Mininet)

## 📌 Overview

This project demonstrates a **Software Defined Networking (SDN)** system using the POX controller and Mininet. It implements:

* Reactive L2 forwarding (learning switch)
* Traffic monitoring with JSON logging
* Dynamic traffic blocking (policy-based)
* Link failure simulation and recovery
* Flow table inspection using Open vSwitch (OVS)

---

## Network Topology

* **Switches:** s1, s2
* **Hosts:** h1, h2, h3, h4

```
h1 ----\
        s1 -------- s2 ---- h3
h2 ----/              \---- h4
```

* h1, h2 connected to **s1**
* h3, h4 connected to **s2**
* s1 and s2 are interconnected

---

## ⚙️ Technologies Used

* Python
* POX Controller
* Mininet
* Open vSwitch (OVS)
* Tshark (optional packet capture)

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

---

### 🔹 Throughput Test

```bash
h4 iperf -s &
h1 iperf -c 10.0.0.4
```

---

### 🔹 Blocked Traffic (Example Policy)

```bash
h2 ping h3
```

> Traffic from h2 → h3 is blocked by controller

---

### 🔹 Link Failure Simulation

```bash
link s1 s2 down
h1 ping h4   # should fail

link s1 s2 up
h1 ping h4   # should recover
```

---

## 📊 Flow Table & Stats (Run in Linux Terminal)

```bash
sudo ovs-ofctl dump-flows s1
sudo ovs-ofctl dump-ports s1
```

---

## 📁 Logs

Log file:

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

* ✅ Learning switch using OpenFlow
* ✅ MAC-to-port mapping
* ✅ Dynamic flow installation
* ✅ Traffic blocking policy
* ✅ JSON-based event logging
* ✅ Link failure handling
* ✅ Flow table inspection

---

## 💡 Key Concept

The controller dynamically manages the network by:

* Installing flows reactively
* Monitoring traffic events
* Enforcing security policies
* Logging network activity

---



Parnika

---
