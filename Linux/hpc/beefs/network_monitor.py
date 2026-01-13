#!/usr/bin/env python3
# name.........: network_monitor
# description..: Network Monitor
# author.......: Alan da Silva Alves
# version......: 2.0.1
# date.........: 1/7/2026
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
#!/usr/bin/env python3
import sys
import time
import os

# --- CONFIGURAÇÃO GLOBAL ---
DEBUG_MODE = False

# --- CORES ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    GREY = '\033[90m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


# --- HELPER: DEBUG ---
def debug_log(msg):
    if DEBUG_MODE:
        print(f"{Colors.GREY}[DEBUG] {msg}{Colors.ENDC}")


def read_file_content(path):
    """Lê um arquivo e loga no debug."""
    debug_log(f"Lendo arquivo: {path}")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            debug_log(f"Erro ao ler {path}: {e}")
    else:
        debug_log(f"Arquivo não encontrado: {path}")
    return ""


def safe_popen(cmd):
    """Executa comando e loga no debug."""
    debug_log(f"Executando comando: {cmd}")
    try:
        stream = os.popen(cmd)
        output = stream.read()
        stream.close()
        return output
    except Exception as e:
        debug_log(f"Erro ao executar comando: {e}")
        return ""


# --- HELP ---
def show_help():
    help_text = f"""
{Colors.HEADER}NET_DIAG - Ferramenta de Diagnóstico de Rede Avançada (Linux){Colors.ENDC}
Autor: Alan Alves

{Colors.BOLD}USO:{Colors.ENDC}
    python3 {sys.argv[0]} [interface] [flags]

{Colors.BOLD}DESCRIÇÃO:{Colors.ENDC}
    Monitora interfaces de rede calculando o DELTA (diferença) de estatísticas
    entre dois momentos no tempo. Diagnostica falhas Físicas, de Hardware (NIC)
    e de Software (Kernel).

{Colors.BOLD}ARGUMENTOS:{Colors.ENDC}
    {Colors.GREEN}interface{Colors.ENDC}      (Opcional) Nome da interface (ex: eth0). Se omitido,
                   o script descobre interfaces físicas automaticamente.

{Colors.BOLD}FLAGS:{Colors.ENDC}
    {Colors.YELLOW}--time <seg>{Colors.ENDC}   Define a duração do teste em segundos (Padrão: 5s).
    {Colors.YELLOW}--debug{Colors.ENDC}        Mostra os arquivos consultados e comandos executados.
    {Colors.YELLOW}--help{Colors.ENDC}         Mostra esta mensagem.

{Colors.BOLD}COMO INTERPRETAR:{Colors.ENDC}
    1. {Colors.RED}[FÍSICO]{Colors.ENDC}: Erros de CRC/Cabo. Troque o cabeamento.
    2. {Colors.RED}[HARDWARE NIC]{Colors.ENDC}: Placa sem buffer. Ajuste com 'ethtool -G'.
    3. {Colors.RED}[KERNEL]{Colors.ENDC}: SO sobrecarregado. Ajuste 'softirq' ou 'backlog'.

{Colors.BOLD}EXEMPLOS:{Colors.ENDC}
    python3 {sys.argv[0]} --time 10
    python3 {sys.argv[0]} eth0 --debug
    """
    print(help_text)
    sys.exit(0)


# --- PARSE DE ARGUMENTOS ---
def parse_args():
    global DEBUG_MODE
    args = sys.argv[1:]
    
    # Flags Booleanas
    if "--help" in args or "-h" in args:
        show_help()
    
    if "--debug" in args:
        DEBUG_MODE = True
        args = [a for a in args if a != "--debug"]

    # Flag com Valor (--time)
    duration = 5
    clean_args = []
    skip_next = False
    
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
            
        if arg == "--time":
            if i + 1 < len(args):
                try:
                    duration = int(args[i+1])
                    skip_next = True
                except ValueError:
                    print(f"{Colors.RED}Erro: Valor inválido para --time.{Colors.ENDC}")
                    sys.exit(1)
            else:
                print(f"{Colors.RED}Erro: --time requer um valor em segundos.{Colors.ENDC}")
                sys.exit(1)
        else:
            clean_args.append(arg)

    return clean_args, duration


# --- FUNÇÕES DE DESCOBERTA ---
def check_requirements():
    if not safe_popen("which ethtool").strip():
        print(f"{Colors.RED}Erro: 'ethtool' não encontrado no sistema.{Colors.ENDC}")
        sys.exit(1)


def get_master_interface(iface):
    path = f"/sys/class/net/{iface}/master"
    if os.path.exists(path):
        try:
            # Debug manual aqui pois os.readlink não usa nosso wrapper
            if DEBUG_MODE: print(f"{Colors.GREY}[DEBUG] Lendo symlink: {path}{Colors.ENDC}")
            return os.path.basename(os.readlink(path))
        except OSError: return None
    return None


def discover_interfaces():
    debug_log("Iniciando descoberta automática de interfaces...")
    target_ifaces = []
    try:
        all_ifaces = os.listdir('/sys/class/net')
    except OSError: return []

    for iface in all_ifaces:
        if iface == 'lo': continue
        
        state = read_file_content(f"/sys/class/net/{iface}/operstate")
        if state == "down": continue
        
        # Ignora interfaces Master (Bonding)
        if os.path.exists(f"/sys/class/net/{iface}/bonding"):
            debug_log(f"Ignorando Master Bond: {iface}")
            continue 
        
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
    content = read_file_content("/proc/stat")
    if content:
        line = content.splitlines()[0]
        parts = line.split()
        softirq = int(parts[7])
        total = sum(int(x) for x in parts[1:])
        return total, softirq
    return 0, 0


def get_kernel_stats(iface):
    base_path = f"/sys/class/net/{iface}/statistics"
    stats = {}
    # Lista explícita de arquivos para o debug mostrar um por um
    for f_name in ['rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors']:
        val_str = read_file_content(f"{base_path}/{f_name}")
        stats[f_name] = int(val_str) if val_str.isdigit() else 0
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

    # Analisar Hardware
    for key in e_end:
        start_v, end_v = e_start.get(key, 0), e_end[key]
        if any(x in key.lower() for x in phy_keys):
            if fmt_err(key, start_v, end_v, "FÍSICO"):
                phy_detected, found_issue = True, True
        elif any(x in key.lower() for x in nic_keys):
            if fmt_err(key, start_v, end_v, "HARDWARE NIC"):
                nic_detected, found_issue = True, True

    # Analisar Kernel
    for key in k_end:
        if fmt_err(key, k_start.get(key, 0), k_end[key], "KERNEL"):
            found_issue = True

    # Sugestões
    if phy_detected:
        print(f"   {Colors.YELLOW}-> AÇÃO: Falha de integridade. Verifique cabos, interferência RF ou porta do switch.{Colors.ENDC}")
    
    if nic_detected:
        curr, maximum = get_ring_buffer_info(iface)
        if maximum > 0:
            print(f"   {Colors.YELLOW}-> AÇÃO: Gargalo na placa. Aumente o Ring Buffer.")
            print(f"      Status: {curr} de {maximum} suportados. Comando: ethtool -G {iface} rx {maximum}{Colors.ENDC}")
        else:
            print(f"   {Colors.YELLOW}-> AÇÃO: Descarte interno no hardware.")
            print(f"      Nota: Hardware não suporta ajuste de buffer (comum em USB/Wi-Fi/Virtio).")
            print(f"      Causa: Gargalo no barramento ou saturação do chip.{Colors.ENDC}")

    if found_issue and not (phy_detected or nic_detected):
        if si_percent > 10.0:
            print(f"   {Colors.YELLOW}-> AÇÃO: Alta carga de CPU detectada ({si_percent:.1f}% em softirq).{Colors.ENDC}")
        else:
            print(f"   {Colors.YELLOW}-> AÇÃO: Ajustar 'sysctl net.core.netdev_max_backlog'.{Colors.ENDC}")

    if not found_issue:
        msg = f"A placa {iface} é parte da interface {master}" if master else f"Interface {iface}"
        print(f"   {Colors.GREEN}[OK] {msg} foi verificada e está saudável.{Colors.ENDC}")


# --- MAIN ---
def main():
    ifaces_to_monitor, duration = parse_args()
    check_requirements()

    if not ifaces_to_monitor:
        ifaces_to_monitor = discover_interfaces()

    if not ifaces_to_monitor:
        print(f"{Colors.RED}Nenhuma interface ativa encontrada.{Colors.ENDC}")
        sys.exit(0)
    
    # Mapa de Master/Slave
    iface_map = {iface: get_master_interface(iface) for iface in ifaces_to_monitor}
    
    print(f"{Colors.BLUE}Iniciando coleta por {Colors.BOLD}{duration} segundos{Colors.ENDC}{Colors.BLUE}...{Colors.ENDC}")
    
    # Coleta Inicial
    start_data = {}
    for iface in ifaces_to_monitor:
        speed, duplex = get_link_status(iface)
        m_info = f" (Parte de {iface_map[iface]})" if iface_map[iface] else ""
        print(f" - {iface}{m_info}: {speed} / {duplex}")
        start_data[iface] = {'k': get_kernel_stats(iface), 'e': get_ethtool_stats(iface)}
    
    cpu_tot_s, cpu_si_s = get_cpu_softirq()

    # Sleep
    try:
        if DEBUG_MODE: debug_log(f"Dormindo por {duration} segundos...")
        time.sleep(duration)
    except KeyboardInterrupt:
        print("\nCancelado pelo usuário.")
        sys.exit(0)

    # Coleta Final
    cpu_tot_e, cpu_si_e = get_cpu_softirq()
    cpu_load = {'total': cpu_tot_e - cpu_tot_s, 'si': cpu_si_e - cpu_si_s}

    for iface in ifaces_to_monitor:
        analyze_results(
            iface, iface_map[iface],
            start_data[iface]['k'], get_kernel_stats(iface),
            start_data[iface]['e'], get_ethtool_stats(iface),
            cpu_load
        )


if __name__ == "__main__":
    main()
