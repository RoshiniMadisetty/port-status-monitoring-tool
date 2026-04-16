#!/bin/bash
# =============================================================================
# SDN Port Status Monitor - Setup & Run Script
# =============================================================================
set -e

POXDIR="$HOME/pox"
PROJDIR="$(cd "$(dirname "$0")" && pwd)"
CONTROLLER="$PROJDIR/controller/port_monitor.py"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
header(){ echo -e "\n${BOLD}${CYAN}=== $1 ===${NC}\n"; }

# ─── Functions ────────────────────────────────────────────────────────────────

check_deps() {
    header "Checking Dependencies"
    command -v python3    >/dev/null || error "python3 not found"
    command -v mn         >/dev/null || error "Mininet (mn) not found - run: sudo apt install mininet"
    command -v ovs-vsctl  >/dev/null || error "Open vSwitch not found"
    command -v ovs-ofctl  >/dev/null || error "ovs-ofctl not found"
    ok "All dependencies found"
}

install_pox() {
    header "Setting Up POX Controller"
    if [ ! -d "$POXDIR" ]; then
        info "Cloning POX..."
        git clone https://github.com/noxrepo/pox.git "$POXDIR"
        ok "POX cloned to $POXDIR"
    else
        ok "POX already at $POXDIR"
    fi

    # Copy controller into POX
    cp "$CONTROLLER" "$POXDIR/ext/port_monitor.py"
    ok "Controller copied to $POXDIR/ext/"
}

clean_mininet() {
    header "Cleaning Mininet State"
    sudo mn --clean 2>/dev/null || true
    sudo pkill -f "pox.py"     2>/dev/null || true
    sudo rm -f /tmp/sdn_port_monitor.log
    ok "Mininet state cleaned"
}

start_controller() {
    header "Starting POX Controller"
    info "Controller log: /tmp/pox_controller.log"
    cd "$POXDIR"
    nohup python3 pox.py log.level --DEBUG openflow.of_01 port_monitor \
        > /tmp/pox_controller.log 2>&1 &
    CPID=$!
    echo $CPID > /tmp/pox_pid
    info "POX PID: $CPID"
    info "Waiting for controller to start..."
    sleep 4
    if kill -0 $CPID 2>/dev/null; then
        ok "Controller started (PID $CPID)"
    else
        error "Controller failed to start. Check /tmp/pox_controller.log"
    fi
}

start_topology() {
    local SCENARIO="${1:-}"
    header "Starting Mininet Topology"
    if [ -n "$SCENARIO" ]; then
        info "Running scenario: $SCENARIO"
        sudo python3 "$PROJDIR/topology.py" "$SCENARIO"
    else
        sudo python3 "$PROJDIR/topology.py"
    fi
}

start_dashboard() {
    header "Starting Monitor Dashboard"
    python3 "$PROJDIR/monitor_dashboard.py"
}

show_flows() {
    header "Current Flow Tables"
    for SW in s1 s2 s3; do
        echo -e "${CYAN}--- $SW ---${NC}"
        sudo ovs-ofctl dump-flows $SW 2>/dev/null || echo "  (not running)"
    done
}

show_ports() {
    header "Current Port Statistics"
    for SW in s1 s2 s3; do
        echo -e "${CYAN}--- $SW ---${NC}"
        sudo ovs-ofctl dump-ports $SW 2>/dev/null || echo "  (not running)"
    done
}

show_log() {
    header "Controller Event Log (last 40 lines)"
    tail -40 /tmp/sdn_port_monitor.log 2>/dev/null || echo "Log not found"
}

stop_all() {
    header "Stopping All Components"
    if [ -f /tmp/pox_pid ]; then
        kill $(cat /tmp/pox_pid) 2>/dev/null && ok "Controller stopped"
        rm -f /tmp/pox_pid
    fi
    sudo mn --clean 2>/dev/null || true
    ok "Cleanup complete"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

case "${1:-help}" in
    setup)
        check_deps
        install_pox
        ok "Setup complete! Run: ./run.sh start"
        ;;
    start)
        check_deps
        clean_mininet
        install_pox
        start_controller
        echo ""
        info "Controller is running. Open a NEW terminal and run:"
        info "  sudo python3 topology.py        (interactive CLI)"
        info "  sudo python3 topology.py all    (run all scenarios)"
        info "  python3 monitor_dashboard.py    (live dashboard)"
        ;;
    topo|topology)
        start_topology "${2:-}"
        ;;
    dashboard)
        start_dashboard
        ;;
    scenario)
        clean_mininet
        install_pox
        start_controller
        sleep 2
        start_topology "${2:-all}"
        ;;
    flows)
        show_flows
        ;;
    ports)
        show_ports
        ;;
    log)
        show_log
        ;;
    stop)
        stop_all
        ;;
    clean)
        clean_mininet
        ;;
    help|*)
        echo -e "${BOLD}SDN Port Status Monitor - Run Script${NC}"
        echo ""
        echo "Usage: $0 <command> [scenario]"
        echo ""
        echo "Commands:"
        echo "  setup       - Install POX and verify dependencies"
        echo "  start       - Clean, install, and start controller"
        echo "  topo        - Start Mininet topology (optional: scenario name)"
        echo "  dashboard   - Start live monitoring dashboard"
        echo "  scenario    - Start controller + run a scenario"
        echo "  flows       - Dump OVS flow tables"
        echo "  ports       - Dump OVS port stats"
        echo "  log         - Show controller event log"
        echo "  stop        - Stop all components"
        echo "  clean       - Clean Mininet state only"
        echo ""
        echo "Scenarios: allowed | blocked | failure | monitor | all"
        echo ""
        echo "Quick Demo:"
        echo "  Terminal 1: ./run.sh start"
        echo "  Terminal 2: sudo python3 topology.py all"
        echo "  Terminal 3: python3 monitor_dashboard.py"
        ;;
esac
