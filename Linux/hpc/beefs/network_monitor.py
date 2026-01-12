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
    """Lê o argumento --time da linha de comando."""
    duration = 5 
    if "--time" in sys.argv:
        try:
            idx = sys.argv.index("--time")
            val = int(sys.argv[idx + 1])
            if val > 0: duration = val
        except (IndexError, ValueError):
            pass
    return duration


def safe_popen(cmd):
    try:
        stream = os.popen(cmd)
        output = stream.read()
        stream.close()
        return output
    except:
        return ""

def check_requirements():
    if not safe_popen("which ethtool").strip():
        print(f"{Colors.RED}Erro: 'ethtool' não encontrado.{Colors.ENDC}")
        sys.exit(1)

# --- IDENTIFICAÇÃO DE TOPOLOGIA ---
def get_master_interface(iface):
    """Retorna o nome da interface Master (bond/bridge) se existir."""
    master_path = f"/sys/class/net/{iface}/master"
    if os.path.exists(master_path):
        try:
            # O link geralmente aponta para ../../bond0, pegamos apenas o nome final
            return os.path.basename(os.readlink(master_path))
        except OSError:
            return None
    return None


def discover_interfaces():
    """Retorna lista de interfaces UP, excluindo Bond Masters."""
    target_ifaces = []
    try:
        all_ifaces = os.listdir('/sys/class/net')
    except OSError:
        print(f"{Colors.RED}Erro: Não foi possível ler /sys/class/net{Colors.ENDC}")
        sys.exit(1)

    for iface in all_ifaces:
        if iface == 'lo': continue
        
        # 1. Checar se está UP
        try:
            with open(f"/sys/class/net/{iface}/operstate", 'r') as f:
                state = f.read().strip()
            # Aceitamos 'up' ou 'unknown' (algumas virtuais ficam unknown)
            if state == "down": continue
        except: continue

        # 2. Checar se é Bond Master (Devemos ignorar)
        if os.path.exists(f"/sys/class/net/{iface}/bonding"):
            continue 
        
        target_ifaces.append(iface)

    return target_ifaces


# --- COLETA DE DADOS ---
def get_link_status(iface):
    out = safe_popen(f"ethtool {iface} 2>/dev/null")
    speed = "Desc."
    duplex = "Desc."
    for line in out.splitlines():
        if "Speed:" in line: speed = line.split(":")[1].strip()
        if "Duplex:" in line: duplex = line.split(":")[1].strip()
    return speed, duplex


def get_ring_buffer_info(iface):
    out = safe_popen(f"ethtool -g {iface} 2>/dev/null")
    max_rx = 0
    curr_rx = 0
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
            softirq = int(parts[7])
            total = sum(int(x) for x in parts[1:])
            return total, softirq
    except:
        return 0, 0


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
def analyze_results(iface, master, k_delta, e_delta, cpu_load):
    found_issue = False
    
    # Header formatado com a informação do MASTER
    topo_info = ""
    if master:
        topo_info = f"{Colors.CYAN}(Parte de {Colors.BOLD}{master}{Colors.ENDC}{Colors.CYAN}){Colors.ENDC}"
    else:
        topo_info = "(Standalone)"

    print(f"\n{Colors.HEADER}>>> RESULTADOS PARA: {Colors.BOLD}{iface}{Colors.ENDC} {topo_info}")

    # 1. CPU
    si_percent = 0
    if cpu_load['total'] > 0:
        si_percent = (cpu_load['si'] / cpu_load['total']) * 100

    # 2. FÍSICO
    phy_errs = 0
    phy_keys = ['crc', 'fcs', 'symbol', 'align', 'carrier']
    for k, v in e_delta.items():
        if any(x in k.lower() for x in phy_keys) and v > 0:
            print(f"   {Colors.RED}[FÍSICO] {k}: +{v}{Colors.ENDC}")
            phy_errs += 1
            found_issue = True
    
    if phy_errs > 0:
        print(f"   {Colors.YELLOW}-> AÇÃO: Problema no cabo/porta física.{Colors.ENDC}")

    # 3. NIC HARDWARE
    nic_errs = 0
    nic_keys = ['fifo', 'missed', 'overrun', 'no_buffer', 'discard', 'drop']
    for k, v in e_delta.items():
        is_phy = any(x in k.lower() for x in phy_keys)
        if not is_phy and any(x in k.lower() for x in nic_keys) and v > 0:
            print(f"   {Colors.RED}[HARDWARE NIC] {k}: +{v}{Colors.ENDC}")
            nic_errs += 1
            found_issue = True
    
    if nic_errs > 0:
        curr, maximum = get_ring_buffer_info(iface)
        print(f"   {Colors.YELLOW}-> AÇÃO: Aumentar Ring Buffer (ethtool -G).{Colors.ENDC}")
        if curr and maximum:
            print(f"      Atual: {curr} | Máx Suportado: {maximum}")

    # 4. KERNEL
    rx_drop = k_delta.get('rx_dropped', 0)
    if rx_drop > 0:
        found_issue = True
        print(f"   {Colors.RED}[KERNEL] rx_dropped: +{rx_drop}{Colors.ENDC}")
        
        if nic_errs == 0 and phy_errs == 0:
            if si_percent > 10.0:
                 print(f"   {Colors.YELLOW}-> AÇÃO: Alta carga de CPU (SoftIRQ {si_percent:.1f}%).{Colors.ENDC}")
            else:
                 print(f"   {Colors.YELLOW}-> AÇÃO: Aumentar netdev_max_backlog.{Colors.ENDC}")

    if not found_issue:
        # Mensagem de sucesso personalizada conforme pedido
        if master:
            print(f"   {Colors.GREEN}[OK] A placa {iface} parte da interface {master} foi verificada e está saudável.{Colors.ENDC}")
        else:
            print(f"   {Colors.GREEN}[OK] Interface {iface} verificada e está saudável.{Colors.ENDC}")


# --- MAIN ---
def main():
    check_requirements()
    duration = get_arg_time()
    
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    
    if args:
        ifaces_to_monitor = args
        print(f"{Colors.BLUE}Modo Manual: Monitorando {len(ifaces_to_monitor)} interface(s)...{Colors.ENDC}")
    else:
        ifaces_to_monitor = discover_interfaces()
        print(f"{Colors.BLUE}Modo Automático: {len(ifaces_to_monitor)} interfaces físicas encontradas.{Colors.ENDC}")
    
    if not ifaces_to_monitor:
        print(f"{Colors.RED}Nenhuma interface elegível encontrada.{Colors.ENDC}")
        sys.exit(0)

    # Dicionário para guardar o mapeamento de interface -> master
    iface_map = {}
    
    print(f"Iniciando coleta ({duration}s)...")
    
    # 1. Coleta Inicial
    start_data = {}
    for iface in ifaces_to_monitor:
        master = get_master_interface(iface)
        iface_map[iface] = master # Salva para usar no print final
        
        speed, duplex = get_link_status(iface)
        
        # Print formatado na inicialização
        if master:
            print(f" - {iface} (Parte de {master}): {speed} / {duplex}")
        else:
            print(f" - {iface}: {speed} / {duplex}")
            
        start_data[iface] = {
            'k': get_kernel_stats(iface),
            'e': get_ethtool_stats(iface)
        }
    
    cpu_tot_s, cpu_si_s = get_cpu_softirq()

    # 2. Aguarda
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(0)

    # 3. Coleta Final e Análise
    cpu_tot_e, cpu_si_e = get_cpu_softirq()
    cpu_load = {'total': cpu_tot_e - cpu_tot_s, 'si': cpu_si_e - cpu_si_s}

    for iface in ifaces_to_monitor:
        k_end = get_kernel_stats(iface)
        e_end = get_ethtool_stats(iface)
        
        k_start = start_data[iface]['k']
        e_start = start_data[iface]['e']
        
        k_delta = {k: k_end.get(k, 0) - k_start.get(k, 0) for k in k_start}
        e_delta = {k: v - e_start.get(k, 0) for k, v in e_end.items() if (v - e_start.get(k, 0)) > 0}
        
        # Passamos o master map para a análise
        analyze_results(iface, iface_map[iface], k_delta, e_delta, cpu_load)


if __name__ == "__main__":
    main()
