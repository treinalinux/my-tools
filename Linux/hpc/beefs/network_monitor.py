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
import sys
import time
import os

# --- CONFIGURAÇÃO GLOBAL ---
DEBUG_MODE = False

# --- CORES E FORMATAÇÃO ---
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


# --- FUNÇÕES DE AJUDA E DEBUG ---
def debug_log(msg):
    """Imprime mensagens de debug se a flag --debug estiver ativa."""
    if DEBUG_MODE:
        print(f"{Colors.GREY}[DEBUG] {msg}{Colors.ENDC}")


def show_help():
    """Exibe o menu de ajuda e encerra."""
    help_text = f"""
{Colors.HEADER}{Colors.BOLD}Network Monitor - Auditor de Integridade de Rede (Linux){Colors.ENDC}

{Colors.BOLD}USO:{Colors.ENDC}
    python3 {sys.argv[0]} [interface] [opções]

{Colors.BOLD}DESCRIÇÃO:{Colors.ENDC}
    Monitora interfaces de rede calculando o DELTA (diferença) de estatísticas
    entre dois momentos. Cruza dados de Hardware (ethtool) e Kernel (sysfs)
    para identificar gargalos Físicos, de Driver ou de Software/CPU.

{Colors.BOLD}OPÇÕES:{Colors.ENDC}
    {Colors.GREEN}interface{Colors.ENDC}      (Opcional) Nome da interface (ex: eth0). Se omitido,
                   o script descobre interfaces físicas automaticamente.

    {Colors.YELLOW}--time <seg>{Colors.ENDC}   Duração do teste em segundos (Padrão: 5s).
    {Colors.YELLOW}--debug{Colors.ENDC}        Modo verboso: mostra arquivos lidos e comandos.
    {Colors.YELLOW}--help, -h{Colors.ENDC}     Mostra esta mensagem de ajuda.

{Colors.BOLD}COMO INTERPRETAR O DIAGNÓSTICO:{Colors.ENDC}
    1. {Colors.RED}[FÍSICO]{Colors.ENDC}: Erros de CRC, Sinal ou Cabo.
       -> Ação: Trocar cabeamento ou porta do switch.
    
    2. {Colors.RED}[HARDWARE NIC]{Colors.ENDC}: Placa descartando pacotes (FIFO/Missed).
       -> Ação: Aumentar Ring Buffer ('ethtool -G') ou verificar barramento.

    3. {Colors.RED}[LINK]{Colors.ENDC}: Colisões.
       -> Ação: Verificar negociação de Duplex (Half vs Full).

    4. {Colors.RED}[KERNEL]{Colors.ENDC}: Descarte por software (Overrun/Dropped).
       -> Ação: Verificar carga de CPU (SoftIRQ) ou aumentar 'netdev_max_backlog'.

{Colors.BOLD}EXEMPLOS:{Colors.ENDC}
    # Modo automático (5 segundos):
    python3 {sys.argv[0]}

    # Monitorar eth0 por 10 segundos com debug:
    python3 {sys.argv[0]} eth0 --time 10 --debug
    """
    print(help_text)
    sys.exit(0)


# --- FUNÇÕES DE SISTEMA (WRAPPERS) ---
def read_file_content(path):
    """Lê um arquivo do sysfs de forma segura."""
    debug_log(f"Lendo arquivo: {path}")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            debug_log(f"Erro ao ler {path}: {e}")
            return "0"
    else:
        debug_log(f"Arquivo não encontrado: {path}")
    return "0"


def safe_popen(cmd):
    """Executa comando no shell e retorna a saída."""
    debug_log(f"Executando: {cmd}")
    try:
        stream = os.popen(cmd)
        output = stream.read()
        stream.close()
        return output
    except Exception as e:
        debug_log(f"Erro na execução: {e}")
        return ""


def check_requirements():
    if not safe_popen("which ethtool").strip():
        print(f"{Colors.RED}Erro Crítico: O comando 'ethtool' não foi encontrado.{Colors.ENDC}")
        print("Instale-o via: apt install ethtool / yum install ethtool")
        sys.exit(1)


# --- PARSER DE ARGUMENTOS ---
def parse_args():
    global DEBUG_MODE
    args = sys.argv[1:]
    
    # Checagem de Help
    if "--help" in args or "-h" in args:
        show_help()
    
    # Checagem de Debug
    if "--debug" in args:
        DEBUG_MODE = True
        args = [a for a in args if a != "--debug"]

    duration = 5
    ifaces = []
    skip_next = False
    
    # Loop manual para garantir que --time funcione em qualquer posição
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
                print(f"{Colors.RED}Erro: A flag --time requer um número.{Colors.ENDC}")
                sys.exit(1)
        else:
            if not arg.startswith("-"):
                ifaces.append(arg)

    return ifaces, duration


# --- DESCOBERTA E TOPOLOGIA ---
def get_master_interface(iface):
    """Retorna o nome da interface Master (Bond/Bridge) se existir."""
    path = f"/sys/class/net/{iface}/master"
    if os.path.exists(path):
        try:
            # os.readlink não usa o wrapper pois retorna path, não conteúdo
            if DEBUG_MODE: debug_log(f"Lendo symlink: {path}")
            return os.path.basename(os.readlink(path))
        except OSError: return None
    return None


def discover_interfaces():
    """Retorna lista de interfaces físicas UP (excluindo Bond Masters)."""
    debug_log("Iniciando descoberta automática...")
    target_ifaces = []
    try:
        all_ifaces = os.listdir('/sys/class/net')
    except OSError: return []

    for iface in all_ifaces:
        if iface == 'lo': continue
        
        # Ignora interfaces DOWN
        state = read_file_content(f"/sys/class/net/{iface}/operstate")
        if state == "down": continue
        
        # Ignora Interfaces Master (Bonding) - Queremos monitorar as Partes do Master BondX
        if os.path.exists(f"/sys/class/net/{iface}/bonding"):
            debug_log(f"Ignorando Interface Master (Bond): {iface}")
            continue 
        
        target_ifaces.append(iface)
    return target_ifaces


# --- COLETA DE DADOS (SENSORES) ---
def get_interface_config(iface):
    """Lê MTU e Tamanho da Fila (QLen)."""
    mtu = read_file_content(f"/sys/class/net/{iface}/mtu")
    qlen = read_file_content(f"/sys/class/net/{iface}/tx_queue_len")
    return mtu, qlen


def get_link_status(iface):
    """Obtém Velocidade e Duplex via ethtool."""
    out = safe_popen(f"ethtool {iface} 2>/dev/null")
    speed, duplex = "Desc.", "Desc."
    for line in out.splitlines():
        if "Speed:" in line: speed = line.split(":")[1].strip()
        if "Duplex:" in line: duplex = line.split(":")[1].strip()
    return speed, duplex


def get_ring_buffer_info(iface):
    """Verifica limites do Ring Buffer (RX)."""
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
    """Lê /proc/stat para calcular carga de interrupção de software."""
    content = read_file_content("/proc/stat")
    if content:
        line = content.splitlines()[0]
        parts = line.split()
        # softirq é a coluna 7 (índice 7 após o 'cpu')
        softirq = int(parts[7])
        total = sum(int(x) for x in parts[1:])
        return total, softirq
    return 0, 0


def get_kernel_stats(iface):
    """Lê estatísticas vitais do Kernel (simulando ip -s link)."""
    base_path = f"/sys/class/net/{iface}/statistics"
    stats = {}
    # Lista de arquivos cruciais
    keys = [
        'rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors',
        'multicast', 'collisions', 'rx_over_errors', 'rx_frame_errors', 'rx_crc_errors'
    ]
    for key in keys:
        val_str = read_file_content(f"{base_path}/{key}")
        stats[key] = int(val_str) if val_str.isdigit() else 0
    return stats


def get_ethtool_stats(iface):
    """Lê estatísticas proprietárias do driver/hardware."""
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


# --- MOTOR DE ANÁLISE ---
def analyze_results(iface, master, k_start, k_end, e_start, e_end, cpu_load):
    # Contexto de Topologia
    topo_info = f"{Colors.CYAN}(Parte de {Colors.BOLD}{master}{Colors.ENDC}{Colors.CYAN}){Colors.ENDC}" if master else "(Standalone)"
    print(f"\n{Colors.HEADER}>>> RESULTADOS PARA: {Colors.BOLD}{iface}{Colors.ENDC} {topo_info}")

    # Cálculo de CPU SoftIRQ %
    si_percent = 0
    if cpu_load['total'] > 0:
        si_percent = (cpu_load['si'] / cpu_load['total']) * 100

    found_issue = False

    # Função auxiliar de formatação
    def fmt_err(key, start, end, category, is_warn=False):
        delta = end - start
        if delta > 0:
            color = Colors.YELLOW if is_warn else Colors.RED
            print(f"   {color}[{category}] {key}({start}): +{delta} (Total: {end}){Colors.ENDC}")
            return True
        return False

    # 1. ANÁLISE DE HARDWARE (ETHTOOL)
    phy_keys = ['crc', 'fcs', 'symbol', 'align', 'carrier']
    nic_keys = ['fifo', 'missed', 'overrun', 'no_buffer', 'discard', 'drop']
    
    phy_detected = False
    nic_detected = False

    for key in e_end:
        s_val, e_val = e_start.get(key, 0), e_end[key]
        
        if any(x in key.lower() for x in phy_keys):
            if fmt_err(key, s_val, e_val, "FÍSICO"):
                phy_detected = True; found_issue = True
        
        elif any(x in key.lower() for x in nic_keys):
            if fmt_err(key, s_val, e_val, "HARDWARE NIC"):
                nic_detected = True; found_issue = True

    # 2. ANÁLISE DE KERNEL/LINK (SYSFS)
    # Multicast Storm Check
    m_s, m_e = k_start.get('multicast', 0), k_end.get('multicast', 0)
    if (m_e - m_s) > 5000: # Threshold arbitrário para alerta
        print(f"   {Colors.YELLOW}[TRÁFEGO] multicast({m_s}): +{m_e - m_s} (Total: {m_e}) - Atenção: Possível Storm.{Colors.ENDC}")
        found_issue = True

    # Erros de Link e Kernel
    if fmt_err('collisions', k_start.get('collisions',0), k_end.get('collisions',0), "LINK"): found_issue = True
    if fmt_err('rx_over_errors', k_start.get('rx_over_errors',0), k_end.get('rx_over_errors',0), "KERNEL OVERRUN"): found_issue = True
    if fmt_err('rx_frame_errors', k_start.get('rx_frame_errors',0), k_end.get('rx_frame_errors',0), "KERNEL FRAME"): found_issue = True
    if fmt_err('rx_dropped', k_start.get('rx_dropped',0), k_end.get('rx_dropped',0), "KERNEL DROP"): found_issue = True

    # --- RELATÓRIO DE AÇÕES SUGERIDAS ---
    if phy_detected:
        print(f"   {Colors.YELLOW}-> AÇÃO: Falha de integridade física. Verifique cabos, interferência ou porta do switch.{Colors.ENDC}")
    
    if nic_detected:
        curr, maximum = get_ring_buffer_info(iface)
        if maximum > 0:
            print(f"   {Colors.YELLOW}-> AÇÃO: Gargalo na placa. Aumente o Ring Buffer.")
            print(f"      Status: {curr} de {maximum} suportados. Comando: ethtool -G {iface} rx {maximum}{Colors.ENDC}")
        else:
            print(f"   {Colors.YELLOW}-> AÇÃO: Descarte interno no hardware.")
            print(f"      Nota: Hardware (USB/Wi-Fi/Virt) não suporta ajuste de buffer.")
            print(f"      Causa Provável: Saturação do chip ou gargalo no barramento.{Colors.ENDC}")

    # Ações para Link/Kernel
    col_delta = k_end.get('collisions', 0) - k_start.get('collisions', 0)
    if col_delta > 0:
        print(f"   {Colors.YELLOW}-> AÇÃO: Colisões detectadas. Verifique a negociação de DUPLEX.{Colors.ENDC}")

    if found_issue and not (phy_detected or nic_detected):
        if si_percent > 10.0:
            print(f"   {Colors.YELLOW}-> AÇÃO: Alta carga de CPU detectada ({si_percent:.1f}% em softirq). Considere RPS ou upgrade.{Colors.ENDC}")
        else:
            print(f"   {Colors.YELLOW}-> AÇÃO: Aumentar buffers de software: 'sysctl -w net.core.netdev_max_backlog=...' {Colors.ENDC}")

    if not found_issue:
        msg = f"A placa '{iface}' é parte de '{master}'" if master else f"A interface '{iface}'"
        print(f"   {Colors.GREEN}[OK] {msg} verificada e saudável.{Colors.ENDC}")


# --- MAIN ---
def main():
    ifaces_to_monitor, duration = parse_args()
    check_requirements()

    # Se nenhuma interface foi passada, descobrir automaticamente
    if not ifaces_to_monitor:
        ifaces_to_monitor = discover_interfaces()

    if not ifaces_to_monitor:
        print(f"{Colors.RED}Nenhuma interface ativa encontrada para monitoramento.{Colors.ENDC}")
        sys.exit(0)
    
    # Mapear Topology (Quem é Parte de quem)
    iface_map = {iface: get_master_interface(iface) for iface in ifaces_to_monitor}
    
    print(f"{Colors.BLUE}Iniciando coleta por {Colors.BOLD}{duration} segundos{Colors.ENDC}{Colors.BLUE}...{Colors.ENDC}")
    
    # 1. COLETA INICIAL (T0)
    start_data = {}
    for iface in ifaces_to_monitor:
        speed, duplex = get_link_status(iface)
        mtu, qlen = get_interface_config(iface)
        m_info = f" (Parte de {iface_map[iface]})" if iface_map[iface] else ""
        
        # Info Header
        print(f" - {iface}{m_info}: {speed}/{duplex} | MTU: {mtu} | QLen: {qlen}")
        
        start_data[iface] = {
            'k': get_kernel_stats(iface),
            'e': get_ethtool_stats(iface)
        }
    
    cpu_tot_s, cpu_si_s = get_cpu_softirq()

    # 2. JANELA DE AMOSTRAGEM
    try:
        if DEBUG_MODE: debug_log(f"Dormindo {duration}s...")
        time.sleep(duration)
    except KeyboardInterrupt:
        print("\nCancelado pelo usuário.")
        sys.exit(0)

    # 3. COLETA FINAL (T1)
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
