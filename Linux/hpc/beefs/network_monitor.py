#!/usr/bin/env python3
# name.........: network_monitor
# description..: Network Monitor
# author.......: Alan da Silva Alves
# version......: 2.0.0
# date.........: 1/7/2026
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
import sys
import time
import os


# --- CORES E FORMATAÇÃO ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


# --- FUNÇÕES UTILITÁRIAS ---
def get_arg_time():
    duration = 5 
    if "--time" in sys.argv:
        try:
            idx = sys.argv.index("--time")
            val = int(sys.argv[idx + 1])
            if val > 0: duration = val
        except (IndexError, ValueError): pass
    return duration


def safe_popen(cmd):
    try:
        stream = os.popen(cmd)
        output = stream.read()
        stream.close()
        return output
    except: return ""


def check_requirements():
    if not safe_popen("which ethtool").strip():
        print(f"{Colors.RED}Erro: 'ethtool' não encontrado.{Colors.ENDC}")
        sys.exit(1)


def get_master_interface(iface):
    master_path = f"/sys/class/net/{iface}/master"
    if os.path.exists(master_path):
        try: return os.path.basename(os.readlink(master_path))
        except OSError: return None
    return None


def discover_interfaces():
    target_ifaces = []
    try:
        all_ifaces = os.listdir('/sys/class/net')
    except OSError: sys.exit(1)

    for iface in all_ifaces:
        if iface == 'lo': continue
        try:
            with open(f"/sys/class/net/{iface}/operstate", 'r') as f:
                state = f.read().strip()
            if state == "down": continue
        except: continue
        if os.path.exists(f"/sys/class/net/{iface}/bonding"): continue 
        target_ifaces.append(iface)
    return target_ifaces


# --- COLETA DE DADOS ---
def get_link_status(iface):
    out = safe_popen(f"ethtool {iface} 2>/dev/null")
    speed, duplex = "Desc.", "Desc."
    for line in out.splitlines():
        if "Speed:" in line: speed = line.split(":")[1].strip()
        if "Duplex:" in line: duplex = line.split(":")[1].strip()
    return speed, duplex


def get_ring_buffer_info(iface):
    out = safe_popen(f"ethtool -g {iface} 2>/dev/null")
    max_rx, curr_rx = 0, 0
    section = ""
    for line in out.splitlines():
        line = line.strip()
        if "Pre-set maximums" in line: section = "max"
        if "Current hardware settings" in line: section = "curr"
        if "RX:" in line and section:
            try:
                val = int(line.split(":")[1].strip())
                if section == "max": max_rx = val
                if section == "curr": curr_rx = val
            except: pass
    return curr_rx, max_rx


def get_cpu_softirq():
    try:
        with open("/proc/stat", "r") as f:
            parts = f.readline().split()
            softirq, total = int(parts[7]), sum(int(x) for x in parts[1:])
            return total, softirq
    except: return 0, 0


def get_kernel_stats(iface):
    path = f"/sys/class/net/{iface}/statistics"
    stats = {}
    if not os.path.exists(path): return stats
    try:
        for f_name in ['rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors']:
            with open(f"{path}/{f_name}", 'r') as f:
                stats[f_name] = int(f.read())
    except: pass
    return stats


def get_ethtool_stats(iface):
    safe_iface = iface.replace(';', '').replace('&', '')
    out = safe_popen(f"ethtool -S {safe_iface} 2>/dev/null")
    stats = {}
    if not out: return stats
    for line in out.splitlines():
        if ":" in line and "Statistic" not in line:
            parts = line.split(":", 1)
            try: stats[parts[0].strip()] = int(parts[1].strip())
            except: continue
    return stats


# --- ANÁLISE ---
def analyze_results(iface, master, k_start, k_end, e_start, e_end, cpu_load):
    found_issue = False
    topo_info = f"{Colors.CYAN}(Parte de {Colors.BOLD}{master}{Colors.ENDC}{Colors.CYAN}){Colors.ENDC}" if master else "(Standalone)"
    print(f"\n{Colors.HEADER}>>> RESULTADOS PARA: {Colors.BOLD}{iface}{Colors.ENDC} {topo_info}")

    si_percent = (cpu_load['si'] / cpu_load['total']) * 100 if cpu_load['total'] > 0 else 0

    def fmt_err(key, start_val, end_val, category):
        delta = end_val - start_val
        if delta > 0:
            print(f"   {Colors.RED}[{category}] {key}({start_val}): +{delta} (Total: {end_val}){Colors.ENDC}")
            return True
        return False

    phy_keys = ['crc', 'fcs', 'symbol', 'align', 'carrier']
    nic_keys = ['fifo', 'missed', 'overrun', 'no_buffer', 'discard', 'drop']
    
    phy_detected, nic_detected = False, False

    for key in e_end:
        start_v, end_v = e_start.get(key, 0), e_end[key]
        if any(x in key.lower() for x in phy_keys):
            if fmt_err(key, start_v, end_v, "FÍSICO"):
                phy_detected, found_issue = True, True
        elif any(x in key.lower() for x in nic_keys):
            if fmt_err(key, start_v, end_v, "HARDWARE NIC"):
                nic_detected, found_issue = True, True

    for key in k_end:
        if fmt_err(key, k_start.get(key, 0), k_end[key], "KERNEL"):
            found_issue = True

    # --- LÓGICA DE AÇÃO REFINADA ---
    if phy_detected:
        print(f"   {Colors.YELLOW}-> AÇÃO: Falha de integridade. Verifique cabos, interferência RF (Wi-Fi) ou porta do switch.{Colors.ENDC}")
    
    if nic_detected:
        curr, maximum = get_ring_buffer_info(iface)
        if maximum > 0: # Placa Ethernet padrão
            print(f"   {Colors.YELLOW}-> AÇÃO: Gargalo na placa. Aumente o Ring Buffer.")
            print(f"      Status: {curr} de {maximum} suportados. Comando: ethtool -G {iface} rx {maximum}{Colors.ENDC}")
        else: # Placa USB/Wi-Fi ou Virtual
            print(f"   {Colors.YELLOW}-> AÇÃO: A placa descartou pacotes internamente.")
            print(f"      Nota: Este hardware não permite ajuste de Ring Buffer via ethtool.")
            print(f"      Possível Causa: Gargalo no barramento (USB 2.0?) ou saturação do chip da placa.{Colors.ENDC}")

    if found_issue and not (phy_detected or nic_detected):
        if si_percent > 10.0:
            print(f"   {Colors.YELLOW}-> AÇÃO: Alta carga de CPU detectada ({si_percent:.1f}% em softirq).{Colors.ENDC}")

    if not found_issue:
        msg = f"A placa {iface} é parte da interface {master}" if master else f"Interface {iface}"
        print(f"   {Colors.GREEN}[OK] {msg} foi verificada e está saudável.{Colors.ENDC}")


# --- MAIN ---
def main():
    check_requirements()
    duration = get_arg_time()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ifaces_to_monitor = args if args else discover_interfaces()
    iface_map = {iface: get_master_interface(iface) for iface in ifaces_to_monitor}
    
    print(f"{Colors.BLUE}Iniciando coleta ({duration}s)...{Colors.ENDC}")
    start_data = {}
    for iface in ifaces_to_monitor:
        speed, duplex = get_link_status(iface)
        m_info = f" (Parte de {iface_map[iface]})" if iface_map[iface] else ""
        print(f" - {iface}{m_info}: {speed} / {duplex}")
        start_data[iface] = {'k': get_kernel_stats(iface), 'e': get_ethtool_stats(iface)}
    
    cpu_tot_s, cpu_si_s = get_cpu_softirq()
    try: time.sleep(duration)
    except KeyboardInterrupt: sys.exit(0)
    cpu_tot_e, cpu_si_e = get_cpu_softirq()
    cpu_load = {'total': cpu_tot_e - cpu_tot_s, 'si': cpu_si_e - cpu_si_s}

    for iface in ifaces_to_monitor:
        analyze_results(iface, iface_map[iface], start_data[iface]['k'], get_kernel_stats(iface),
                        start_data[iface]['e'], get_ethtool_stats(iface), cpu_load)


if __name__ == "__main__":
    main()
