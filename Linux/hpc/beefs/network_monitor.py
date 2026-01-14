#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name.........: network_monitor
# description..: Ferramenta de Diagnóstico de Rede Avançada para Linux
# author.......: Alan da Silva Alves
# version......: 2.2.1
# date.........: 1/7/2026
# depends......: ethtool
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
    BOLD = '\033[1m'
    ENDC = '\033[0m'


# --- FUNÇÕES DE LOGGING ---
def debug_log(ctx, msg):
    """Loga apenas se DEBUG_MODE estiver ativo."""
    if DEBUG_MODE:
        print(f"{Colors.GREY}[DEBUG] {ctx:<10} {msg}{Colors.ENDC}")


def show_help():
    """Exibe o manual completo de uso e resolução de problemas."""
    print(f"""
{Colors.HEADER}{Colors.BOLD}Network Monitor - Auditor de Integridade de Rede (Linux){Colors.ENDC}

{Colors.BOLD}DESCRIÇÃO:{Colors.ENDC}
    Ferramenta de análise de variação (delta) em tempo real. Ela captura o estado
    dos contadores de rede no tempo T0, aguarda N segundos, e captura em T1.
    Cruza dados do Hardware (ethtool), Kernel (sysfs) e Protocolos (procfs)
    para isolar a causa raiz de lentidão ou perda de pacotes.

{Colors.BOLD}USO:{Colors.ENDC}
    python3 {sys.argv[0]} [interface] [flags]

{Colors.BOLD}FLAGS:{Colors.ENDC}
    {Colors.GREEN}--time <seg>{Colors.ENDC}   Define a duração da amostragem (Padrão: 5s).
    {Colors.GREEN}--debug{Colors.ENDC}        Modo verboso. Mostra quais arquivos/comandos são lidos.
    {Colors.GREEN}--help, -h{Colors.ENDC}     Exibe este manual.

{Colors.BOLD}GUIA DE SOLUÇÃO DE PROBLEMAS (TROUBLESHOOTING):{Colors.ENDC}

  {Colors.RED}1. ERRO: [FÍSICO] crc, fcs, symbol, align, carrier{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} O pacote chegou corrompido eletricamente/oticamente.
     {Colors.BOLD}Ação:{Colors.ENDC}
       - Trocar o cabo de rede (Cat6/Cat6a) ou Fibra.
       - Limpar/Trocar o transceptor (GBIC/SFP).
       - Trocar a porta do switch.

  {Colors.RED}2. ERRO: [HARDWARE] missed, fifo, overrun, no_buffer{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} O pacote chegou íntegro, mas a placa de rede estava
     sem memória interna (Ring Buffer) para processá-lo.
     {Colors.BOLD}Ação:{Colors.ENDC}
       - Aumentar o Ring Buffer: {Colors.YELLOW}ethtool -G <iface> rx 4096{Colors.ENDC}
       - Se for VM/USB: Limitação do barramento ou da vCPU do Host.

  {Colors.RED}3. ERRO: [FLOW CONTROL] pause_frames{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} O Switch pediu para o servidor parar de enviar dados.
     {Colors.BOLD}Ação:{Colors.ENDC} O problema NÃO é no servidor. Verifique congestionamento no Switch.

  {Colors.RED}4. ERRO: [LINK] collisions{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} Colisão de pacotes.
     {Colors.BOLD}Ação:{Colors.ENDC} Verifique negociação de Duplex. Force Full Duplex no Switch.

  {Colors.RED}5. ERRO: [KERNEL] rx_dropped / rx_over_errors{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} O Kernel recebeu o pacote da placa, mas descartou.
     {Colors.BOLD}Diagnóstico Cruzado:{Colors.ENDC}
       A. {Colors.BOLD}Se [APP/UDP] RcvBufErrors subir junto:{Colors.ENDC}
          Culpa da Aplicação (Java/Nginx/DNS) que está lenta. Aumente:
          {Colors.YELLOW}sysctl -w net.core.rmem_max=26214400{Colors.ENDC}
       B. {Colors.BOLD}Se a CPU (SoftIRQ) estiver > 10%:{Colors.ENDC}
          Culpa da CPU. Habilite RPS (Receive Packet Steering) ou troque CPU.
       C. {Colors.BOLD}Se nenhum dos acima:{Colors.ENDC}
          Backlog do Kernel cheio. Aumente:
          {Colors.YELLOW}sysctl -w net.core.netdev_max_backlog=5000{Colors.ENDC}

  {Colors.RED}6. ERRO: [TCP] Retransmits{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} Pacotes perdidos na internet/WAN. Servidor está OK.
     {Colors.BOLD}Ação:{Colors.ENDC} Diagnóstico de rota (MTR/Traceroute) ou provedor.

  {Colors.RED}7. ERRO: [FIREWALL] Conntrack Full{Colors.ENDC}
     {Colors.BOLD}Significado:{Colors.ENDC} Tabela de conexões do Firewall encheu.
     {Colors.BOLD}Ação:{Colors.ENDC} {Colors.YELLOW}sysctl -w net.netfilter.nf_conntrack_max=524288{Colors.ENDC}

{Colors.BOLD}EXEMPLOS:{Colors.ENDC}
    python3 {sys.argv[0]}
    python3 {sys.argv[0]} eth0 --time 10 --debug
""")
    sys.exit(0)


# --- WRAPPERS DE SISTEMA (COMPATIBILIDADE) ---
def read_file(path, ctx):
    """Lê arquivo do sistema de arquivos virtual (/sys, /proc)."""
    debug_log(ctx, f"Lendo: {path}")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            debug_log(ctx, f"Erro ao ler: {e}")
    else:
        debug_log(ctx, f"Arquivo inexistente: {path}")
    return "0"


def run_cmd(cmd, ctx):
    """Executa comando via shell (os.popen para compatibilidade)."""
    debug_log(ctx, f"Exec: {cmd}")
    try:
        stream = os.popen(cmd)
        output = stream.read()
        stream.close()
        return output
    except Exception as e:
        debug_log(ctx, f"Falha na execução: {e}")
        return ""


def check_requirements():
    if not run_cmd("which ethtool", "[SYSTEM]").strip():
        print(f"{Colors.RED}Erro Crítico: O comando 'ethtool' é obrigatório.{Colors.ENDC}")
        print("Instale via: apt install ethtool / yum install ethtool")
        sys.exit(1)


# --- COLETA DE DADOS (SENSORES) ---

def get_tcp_stats():
    """Lê retransmissões TCP globais (/proc/net/snmp)."""
    content = read_file("/proc/net/snmp", "[TCP]")
    try:
        lines = content.splitlines()
        headers, values = [], []
        for line in lines:
            if line.startswith("Tcp:"):
                if "RetransSegs" in line: headers = line.split()
                else: values = line.split()
        if headers and values:
            idx = headers.index("RetransSegs")
            return int(values[idx])
    except: pass
    return 0


def get_udp_errors():
    """Lê erros de buffer de recepção UDP (/proc/net/snmp)."""
    content = read_file("/proc/net/snmp", "[UDP]")
    try:
        lines = content.splitlines()
        headers, values = [], []
        for line in lines:
            if line.startswith("Udp:"):
                if "RcvbufErrors" in line: headers = line.split()
                else: values = line.split()
        if headers and values:
            return int(values[headers.index("RcvbufErrors")])
    except: pass
    return 0


def get_conntrack_stats():
    """Lê uso da tabela de conexões do Netfilter."""
    count_path = "/proc/sys/net/netfilter/nf_conntrack_count"
    max_path = "/proc/sys/net/netfilter/nf_conntrack_max"

    if not os.path.exists(count_path):
        return 0, 0

    curr = int(read_file(count_path, "[FW]"))
    limit = int(read_file(max_path, "[FW]"))
    return curr, limit


def get_driver_info(iface):
    """Pega nome do Driver e Versão do Firmware."""
    out = run_cmd(f"ethtool -i {iface} 2>/dev/null", "[DRV]")
    drv, fw = "N/A", "N/A"
    for line in out.splitlines():
        if "driver:" in line: drv = line.split(":")[1].strip()
        if "firmware-version:" in line: fw = line.split(":")[1].strip()
    return drv, fw


def get_config_info(iface):
    """Pega MTU, Queue Length e Tamanhos de Ring Buffer."""
    mtu = read_file(f"/sys/class/net/{iface}/mtu", "[LINK]")
    qlen = read_file(f"/sys/class/net/{iface}/tx_queue_len", "[LINK]")

    # Ring Buffer
    out = run_cmd(f"ethtool -g {iface} 2>/dev/null", "[RING]")
    max_rx, curr_rx = 0, 0
    section = ""
    for line in out.splitlines():
        line = line.strip()
        if "Pre-set" in line: section = "max"
        if "Current" in line: section = "curr"
        if "RX:" in line and section:
            try:
                val = int(line.split(":")[1].strip())
                if section == "max": max_rx = val
                if section == "curr": curr_rx = val
            except: pass

    return mtu, qlen, curr_rx, max_rx


def get_kernel_stats(iface):
    """Simula o 'ip -s link' lendo direto do sysfs."""
    base = f"/sys/class/net/{iface}/statistics"
    stats = {}
    keys = ['rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors',
            'multicast', 'collisions', 'rx_over_errors', 'rx_frame_errors']
    for k in keys:
        val = read_file(f"{base}/{k}", "[SYSFS]")
        stats[k] = int(val) if val.isdigit() else 0
    return stats


def get_ethtool_stats(iface):
    """Pega estatísticas proprietárias do Hardware."""
    iface_clean = iface.replace(';', '').replace('&', '')
    out = run_cmd(f"ethtool -S {iface_clean} 2>/dev/null", "[ETHTOOL]")
    stats = {}
    if not out: return stats
    for line in out.splitlines():
        if ":" in line and "Statistic" not in line:
            parts = line.split(":", 1)
            try: stats[parts[0].strip()] = int(parts[1].strip())
            except: continue
    return stats


def get_cpu_softirq():
    """Calcula uso de CPU para interrupções de software (Rede)."""
    content = read_file("/proc/stat", "[CPU]")
    if content:
        line = content.splitlines()[0]
        parts = line.split()
        # softirq é a coluna 7 (0-indexed após 'cpu')
        softirq = int(parts[7])
        total = sum(int(x) for x in parts[1:])
        return total, softirq
    return 0, 0


# --- LÓGICA DE DIAGNÓSTICO ---

def analyze_interface(iface, master, start, end, cpu_load):
    topo = f"(Parte de {Colors.BOLD}{master}{Colors.ENDC})" if master else "(Standalone)"
    drv, fw = start['drv']

    print(f"\n{Colors.HEADER}>>> ANÁLISE: {Colors.BOLD}{iface}{Colors.ENDC} {Colors.CYAN}{topo}{Colors.ENDC}")
    print(f"    {Colors.GREY}Info: Driver={drv} | FW={fw}{Colors.ENDC}")

    found_issue = False
    si_percent = 0
    if cpu_load['total'] > 0:
        si_percent = (cpu_load['si'] / cpu_load['total']) * 100

    # --- FUNÇÕES DE PRINT ---
    def print_error(category, key, delta, total, warn=False):
        color = Colors.YELLOW if warn else Colors.RED
        print(f"   {color}[{category}] {key}: +{delta} (Total: {total}){Colors.ENDC}")

    def suggest(cmd, reason):
        print(f"      {Colors.BOLD}Sugestão:{Colors.ENDC} {reason}")
        print(f"      {Colors.GREEN}Cmd:{Colors.ENDC} {cmd}")

    # 1. HARDWARE (ETHTOOL)
    phy_keys = ['crc', 'fcs', 'symbol', 'align', 'carrier']
    nic_keys = ['fifo', 'missed', 'overrun', 'no_buffer', 'discard', 'drop']
    pause_keys = ['pause']

    phy_hit, nic_hit = False, False

    for k in end['e']:
        s_val, e_val = start['e'].get(k, 0), end['e'][k]
        delta = e_val - s_val

        if delta > 0:
            if any(x in k.lower() for x in phy_keys):
                print_error("FÍSICO", k, delta, e_val)
                phy_hit = True; found_issue = True
            elif any(x in k.lower() for x in nic_keys):
                print_error("HARDWARE", k, delta, e_val)
                nic_hit = True; found_issue = True
            elif any(x in k.lower() for x in pause_keys):
                print_error("FLOW CTRL", k, delta, e_val, warn=True)
                print(f"      {Colors.YELLOW}-> Switch enviando PAUSE frames.{Colors.ENDC}")
                found_issue = True

    if phy_hit:
        print(f"      {Colors.YELLOW}-> DIAGNÓSTICO: Falha física (Cabo/Porta).{Colors.ENDC}")

    if nic_hit:
        curr_rx, max_rx = start['conf'][2], start['conf'][3]
        if max_rx > 0 and curr_rx < max_rx:
            suggest(f"ethtool -G {iface} rx {max_rx}", "Aumentar Ring Buffer para o máximo.")
        else:
            print(f"      {Colors.YELLOW}-> DIAGNÓSTICO: Hardware saturado (Sem margem para buffer).{Colors.ENDC}")

    # 2. KERNEL (SYSFS)
    k_hit = False
    ks, ke = start['k'], end['k']

    # Colisões
    if (ke['collisions'] - ks['collisions']) > 0:
        print_error("LINK", "collisions", ke['collisions']-ks['collisions'], ke['collisions'])
        suggest(f"ethtool -s {iface} duplex full autoneg on", "Forçar Full Duplex.")
        found_issue = True

    # Overruns (CPU Interrupt latency)
    if (ke['rx_over_errors'] - ks['rx_over_errors']) > 0:
        print_error("KERNEL", "rx_over_errors", ke['rx_over_errors']-ks['rx_over_errors'], ke['rx_over_errors'])
        print(f"      {Colors.YELLOW}-> CPU demorou para atender a interrupção.{Colors.ENDC}")
        found_issue = True

    # Drops Puros
    drop_delta = ke['rx_dropped'] - ks['rx_dropped']
    if drop_delta > 0:
        print_error("KERNEL", "rx_dropped", drop_delta, ke['rx_dropped'])
        k_hit = True; found_issue = True

    # 3. GLOBAIS (TCP / UDP / FW)

    # TCP Retransmits (Lentidão de rede externa)
    tcp_delta = end['tcp'] - start['tcp']
    if tcp_delta > 0:
        print_error("TCP", "Retransmits", tcp_delta, end['tcp'], warn=True)
        print(f"      {Colors.YELLOW}-> DIAGNÓSTICO: Perda de pacote na WAN ou Congestionamento.{Colors.ENDC}")
        found_issue = True

    # UDP App Errors (Socket Buffer Full)
    udp_delta = end['udp'] - start['udp']
    app_fault = False
    if udp_delta > 0:
        print_error("APP/UDP", "RcvbufErrors", udp_delta, end['udp'])
        suggest("sysctl -w net.core.rmem_max=26214400", "Aumentar buffer de socket (App lenta).")
        app_fault = True; found_issue = True

    # Firewall (Conntrack)
    ct_curr, ct_max = end['ct']
    if ct_max > 0:
        ct_usage = (ct_curr / ct_max) * 100
        if ct_usage > 90:
            print(f"   {Colors.RED}[FIREWALL] Conntrack Crítico: {ct_curr}/{ct_max} ({ct_usage:.1f}%){Colors.ENDC}")
            suggest("sysctl -w net.netfilter.nf_conntrack_max=524288", "Aumentar tabela de estados.")
            found_issue = True

    # 4. CONCLUSÃO CRUZADA (PARA DROPS DE KERNEL)
    if k_hit:
        if app_fault:
            print(f"      {Colors.CYAN}CAUSA RAIZ:{Colors.ENDC} Aplicação lenta (Não drena o socket).")
        elif si_percent > 10.0:
            print(f"      {Colors.CYAN}CAUSA RAIZ:{Colors.ENDC} CPU Saturada (SoftIRQ {si_percent:.1f}%).")
            print(f"      {Colors.GREEN}Ação:{Colors.ENDC} Verificar 'top' ou configurar RPS (Receive Packet Steering).")
        else:
            print(f"      {Colors.CYAN}CAUSA RAIZ:{Colors.ENDC} Buffer de entrada do Kernel cheio (Backlog).")
            suggest("sysctl -w net.core.netdev_max_backlog=5000", "Aumentar fila de processamento.")

    if not found_issue:
        print(f"   {Colors.GREEN}[OK] Interface Saudável.{Colors.ENDC}")


# --- MAIN FLOW ---

def parse_args():
    global DEBUG_MODE
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        show_help()

    if "--debug" in args:
        DEBUG_MODE = True
        args = [a for a in args if a != "--debug"]

    duration = 5
    ifaces = []
    skip = False

    for i, arg in enumerate(args):
        if skip: skip = False; continue
        if arg == "--time":
            try: duration = int(args[i+1]); skip = True
            except: pass
        else:
            if not arg.startswith("-"):
                ifaces.append(arg)

    return ifaces, duration

def discover_interfaces():
    """Descobre interfaces físicas UP, ignorando bonds."""
    targets = []
    try:
        all_ifaces = os.listdir('/sys/class/net')
    except: return []

    for iface in all_ifaces:
        if iface == 'lo': continue
        if read_file(f"/sys/class/net/{iface}/operstate", "[DISC]") == "down": continue
        if os.path.exists(f"/sys/class/net/{iface}/bonding"): continue
        targets.append(iface)
    return targets

def get_master(iface):
    """Retorna o master (bond/bridge) da interface."""
    path = f"/sys/class/net/{iface}/master"
    if os.path.exists(path):
        try: return os.path.basename(os.readlink(path))
        except: return None
    return None

def main():
    ifaces, duration = parse_args()
    check_requirements()

    if not ifaces:
        ifaces = discover_interfaces()

    if not ifaces:
        print(f"{Colors.RED}Nenhuma interface ativa encontrada.{Colors.ENDC}")
        sys.exit(0)

    masters = {i: get_master(i) for i in ifaces}

    print(f"{Colors.BLUE}Iniciando coleta de baseline por {Colors.BOLD}{duration}s{Colors.ENDC}{Colors.BLUE}...{Colors.ENDC}")

    # Coleta T0
    start_data = {}
    for i in ifaces:
        # Configs estáticas
        mtu, qlen, c_rx, m_rx = get_config_info(i)
        drv, fw = get_driver_info(i)
        topo = f"(Parte de {masters[i]})" if masters[i] else ""

        print(f" - {i} {topo} | MTU:{mtu} | Driver:{drv}")

        start_data[i] = {
            'k': get_kernel_stats(i),
            'e': get_ethtool_stats(i),
            'udp': get_udp_errors(),
            'tcp': get_tcp_stats(),
            'ct': get_conntrack_stats(),
            'conf': (mtu, qlen, c_rx, m_rx),
            'drv': (drv, fw)
        }

    # CPU T0
    cs_tot, cs_si = get_cpu_softirq()

    # Wait
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(0)

    # CPU T1
    ce_tot, ce_si = get_cpu_softirq()
    cpu_load = {'total': ce_tot - cs_tot, 'si': ce_si - cs_si}

    # Coleta T1 e Análise
    for i in ifaces:
        end_data = {
            'k': get_kernel_stats(i),
            'e': get_ethtool_stats(i),
            'udp': get_udp_errors(),
            'tcp': get_tcp_stats(),
            'ct': get_conntrack_stats()
        }
        analyze_interface(i, masters[i], start_data[i], end_data, cpu_load)

if __name__ == "__main__":
    main()
