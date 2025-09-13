#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: monitor_hpc
# description..: Monitor HPC
# author.......: Alan da Silva Alves
# version......: 1.3.7
# date.........: 9/12/2025
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import datetime
import csv
import sys
import time
import json

# --- CONFIGURAÇÕES ---
# Defina os limites para CPU e Memória para considerar "ATENÇÃO"
CPU_THRESHOLD_WARN = 85.0  # em porcentagem
MEM_THRESHOLD_WARN = 85.0  # em porcentagem

# Limites para I/O de disco
IO_AWAIT_THRESHOLD_WARN = 50.0  # Latência de I/O em milissegundos
IO_UTIL_THRESHOLD_WARN = 90.0   # % de utilização do disco

# Limite para o uso agregado de disco do BeeGFS
BEEGFS_USAGE_THRESHOLD_WARN = 90.0 # em porcentagem

# Limites específicos para saúde de SSDs (S.M.A.R.T.)
SSD_PERCENTAGE_USED_THRESHOLD_WARN = 85.0 # % de vida útil consumida
SSD_TEMPERATURE_THRESHOLD_WARN = 70.0     # em Celsius

# Limites para GPUs NVIDIA
GPU_TEMP_THRESHOLD_WARN = 85.0      # em Celsius
GPU_UTIL_THRESHOLD_WARN = 90.0      # em porcentagem

# Limites para Saúde do Sistema
LOAD_AVERAGE_RATIO_WARN = 1.5 # (load_avg / num_cores) - 1.5 significa 50% acima da capacidade total
ZOMBIE_PROCESS_THRESHOLD_WARN = 5 # Número de processos zumbis

# Lista de serviços para monitorar (use os nomes exatos dos serviços no systemd)
SERVICES_TO_CHECK = [
    'beegfs-client',  # Exemplo para BeeGFS
    'grafana-server', # Exemplo para Grafana
    'mysql',          # ou 'mariadb'
    'pacemaker',      # ou 'pcsd'
    'cmdaemon'        # Bright Cluster Manager Daemon
]

# Lista de interfaces de rede a serem ignoradas na verificação de erros
INTERFACES_TO_IGNORE = ['lo', 'virbr']

# --- CAMINHOS PARA OS ARQUIVOS ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
REPORT_DIR = os.path.join(SCRIPT_DIR, 'report')

CSV_LOG_FILE = os.path.join(LOG_DIR, 'hpc_monitoring_log.csv')
HTML_REPORT_FILE = os.path.join(REPORT_DIR, 'hpc_status_report.html')
KB_FILE = os.path.join(SCRIPT_DIR, 'data', 'knowledge_base.json')
TEMPLATE_FILE = os.path.join(SCRIPT_DIR, 'templates', 'report_template.html')
TEST_DATA_FILE = os.path.join(SCRIPT_DIR, 'data', 'test_data.json')


# Palavras-chave para procurar em logs do sistema (ex: dmesg)
HARDWARE_ERROR_KEYWORDS = ['error', 'fail', 'critical', 'fatal', 'segfault']


# --- FUNÇÕES AUXILIARES DE CARREGAMENTO E FORMATAÇÃO ---

def load_json_file(file_path, file_description):
    """Carrega um arquivo JSON e trata possíveis erros."""
    if not os.path.exists(file_path):
        print(f"AVISO: Arquivo de {file_description} '{file_path}' não encontrado.")
        return {} if "base de conhecimento" in file_description else []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                return {} if "base de conhecimento" in file_description else []
            return json.loads(content)
    except json.JSONDecodeError:
        print(f"ERRO: Falha ao decodificar o arquivo JSON de {file_description} '{file_path}'.")
        return {} if "base de conhecimento" in file_description else []

def format_bytes(size_kb):
    """Converte kilobytes para um formato legível (KB, MB, GB, TB)."""
    if size_kb == 0:
        return "0 KB"
    size_names = ("KB", "MB", "GB", "TB")
    i = 0
    size = float(size_kb)
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f} {size_names[i]}"

def get_kb_suggestion(details, knowledge_base):
    """Procura por palavras-chave nos detalhes e retorna uma sugestão da base de conhecimento."""
    for category in knowledge_base.values():
        for keyword, suggestion in category.items():
            if keyword in details:
                return suggestion
    return None

def run_command(command):
    """Executa um comando no shell usando os.popen e retorna a saída e o código de status."""
    pipe = os.popen(f'{command} 2>&1')
    output = pipe.read().strip()
    exit_status = pipe.close()
    code = 0
    if exit_status is not None and os.WIFEXITED(exit_status):
        code = os.WEXITSTATUS(exit_status)
    elif exit_status is not None:
        code = 1
    return output, code


# --- FUNÇÕES DE VERIFICAÇÃO ---

def get_status_level(value, warn_threshold):
    """Retorna o nível de status com base em um valor e um limite."""
    if value >= warn_threshold:
        return 'ATENÇÃO', f'Uso de {value:.1f}% excede o limite de {warn_threshold}%'
    return 'NORMAL', f'Uso de {value:.1f}%'

def get_cpu_times():
    """Lê /proc/stat e retorna os tempos totais e ociosos da CPU."""
    with open('/proc/stat', 'r') as f:
        line = f.readline()
    parts = line.split()
    cpu_times = [int(p) for p in parts[1:9]]
    return sum(cpu_times), cpu_times[3]

def check_cpu_memory():
    """Verifica o uso de CPU e memória RAM usando arquivos nativos do /proc."""
    # Verificação de CPU
    try:
        total1, idle1 = get_cpu_times()
        time.sleep(1)
        total2, idle2 = get_cpu_times()
        delta_total, delta_idle = total2 - total1, idle2 - idle1
        cpu_usage = 100.0 * (delta_total - delta_idle) / delta_total if delta_total > 0 else 0.0
        cpu_status, cpu_msg = get_status_level(cpu_usage, CPU_THRESHOLD_WARN)
        cpu_priority = 'P2 (Alta)' if cpu_status == 'ATENÇÃO' else 'P4 (Informativa)'
    except (IOError, IndexError, ValueError) as e:
        cpu_status, cpu_msg, cpu_priority = 'FALHA', f"Erro ao ler CPU: {e}", 'P1 (Crítica)'

    cpu_result = {'category': 'Recursos de Sistema', 'item': 'Uso de CPU', 'status': cpu_status, 'priority': cpu_priority, 'details': cpu_msg}

    # Verificação de Memória
    try:
        mem_info = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2: mem_info[parts[0].rstrip(':')] = int(parts[1])
        mem_total = mem_info.get('MemTotal', 0)
        mem_available = mem_info.get('MemAvailable', 0) 
        mem_used = mem_total - mem_available
        mem_usage = (mem_used / mem_total) * 100.0 if mem_total > 0 else 0.0
        mem_status, mem_msg = get_status_level(mem_usage, MEM_THRESHOLD_WARN)
        mem_priority = 'P2 (Alta)' if mem_status == 'ATENÇÃO' else 'P4 (Informativa)'
    except (IOError, KeyError, ValueError) as e:
        mem_status, mem_msg, mem_priority = 'FALHA', f"Erro ao ler Memória: {e}", 'P1 (Crítica)'

    mem_result = {'category': 'Recursos de Sistema', 'item': 'Uso de Memória', 'status': mem_status, 'priority': mem_priority, 'details': mem_msg}
    
    return cpu_result, mem_result


def check_infiniband():
    """Verifica o status dos links InfiniBand e a conexão com o switch."""
    _, ibstat_code = run_command("ibstat -V")
    _, iblinkinfo_code = run_command("iblinkinfo -V")
    if ibstat_code != 0 or iblinkinfo_code != 0:
        return None

    full_ibstat_output, code = run_command("ibstat")
    if code != 0:
        return {'category': 'Rede de Alta Performance', 'item': 'InfiniBand Status', 'status': 'FALHA', 'priority': 'P1 (Crítica)', 'details': f"Falha ao executar 'ibstat'. Saída: {full_ibstat_output}"}

    overall_status = 'NORMAL'
    final_details_lines = []
    
    ca_blocks = full_ibstat_output.split('CA \'')
    for block in ca_blocks[1:]:
        lines = block.splitlines()
        ca_name = lines[0].split('\'')[0]
        
        port_details_map = {}
        current_port = None
        for line in lines[1:]:
            line = line.strip()
            if line.startswith('Port '):
                current_port = line.split(':')[0]
                if current_port not in port_details_map:
                    port_details_map[current_port] = {}
            elif ':' in line and current_port:
                key, value = line.split(':', 1)
                port_details_map[current_port][key.strip()] = value.strip()

        link_info_output, _ = run_command(f"iblinkinfo -C {ca_name}")
        switch_connections = {} 
        
        port_link_blocks = link_info_output.split(f'CA: {ca_name} Port ')
        for port_block in port_link_blocks[1:]:
            port_lines = port_block.strip().splitlines()
            if not port_lines: continue
            
            port_num = port_lines[0].split(':')[0]
            port_key = f"Port {port_num}"
            
            switch_info_line = port_lines[1] if len(port_lines) > 1 else ""
            if '==>' in switch_info_line and '"' in switch_info_line:
                try:
                    switch_name = switch_info_line.split('"')[1]
                    switch_port = switch_info_line.split('[')[-1].split(']')[0].strip()
                    switch_connections[port_key] = f'<span style="color: green;">Conectado a: {switch_name} [Porta {switch_port}]</span>'
                except IndexError:
                    switch_connections[port_key] = '<span style="color: red;">Erro ao analisar conexão</span>'
            else:
                switch_connections[port_key] = '<span style="color: red;">Não conectado</span>'

        for port, details in sorted(port_details_map.items()):
            port_state = details.get('State', 'N/A')
            phys_state = details.get('Physical state', 'N/A')
            rate = details.get('Rate', 'N/A')
            link_layer = details.get('Link layer', 'InfiniBand')
            
            # Se for uma porta Ethernet e estiver desabilitada, pule completamente.
            if link_layer == 'Ethernet' and phys_state == 'Disabled':
                continue

            connection = switch_connections.get(port, '<span style="color: red;">Não conectado</span>')
            
            health_part = f"({link_layer}) Estado={port_state}, Físico={phys_state}, Taxa={rate}"
            
            is_problem = False
            # Lógica de cores e status
            if port_state == 'Active' and phys_state == 'LinkUp':
                health_part_colored = f'<span style="color: green;">{health_part}</span>'
            else:
                is_problem = True
                health_part_colored = f'<span style="color: red;">{health_part}</span>'

            if is_problem:
                overall_status = 'ATENÇÃO'
            
            final_details_lines.append(f"{ca_name} - {port}: {health_part_colored} -> {connection}")

    if not final_details_lines:
        return None # Nenhuma porta relevante encontrada, não gere um item no relatório

    final_details = "\n".join(final_details_lines)

    priority = 'P1 (Crítica)' if overall_status == 'FALHA' else ('P2 (Alta)' if overall_status == 'ATENÇÃO' else 'P4 (Informativa)')
    return {'category': 'Rede de Alta Performance', 'item': 'InfiniBand Health & Topology', 'status': overall_status, 'priority': priority, 'details': final_details}

def check_system_errors():
    """Verifica o log do kernel (dmesg) em busca de erros de hardware."""
    dmesg_test_output, dmesg_test_code = run_command("dmesg -T | head -n 1")
    if dmesg_test_code != 0 and "Operation not permitted" in dmesg_test_output:
        return {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'FALHA', 'priority': 'P3 (Média)', 'details': 'Não foi possível ler o buffer do kernel. Execute o script com sudo ou verifique as permissões (sysctl kernel.dmesg_restrict).'}

    grep_pattern = '|'.join(HARDWARE_ERROR_KEYWORDS)
    command = f"dmesg -T | grep -iE '{grep_pattern}'"
    output, code = run_command(command)

    if code == 0 and output:
        output_lines = output.splitlines()
        details_output = "\n".join(output_lines[-20:])
        return {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': f"Encontradas possíveis falhas de hardware ou erros críticos no dmesg:\n{details_output}"}
    elif code > 1:
        return {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'FALHA', 'priority': 'P3 (Média)', 'details': f"Erro ao executar o grep nos logs do dmesg. Saída: {output}"}
    
    return {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'NORMAL', 'priority': 'P4 (Informativa)', 'details': 'Nenhum erro crítico recente encontrado no dmesg.'}

def check_services():
    """Verifica o status dos serviços, ignorando aqueles que não estão instalados."""
    results = []
    for service in SERVICES_TO_CHECK:
        output, _ = run_command(f"systemctl status {service}")
        if "Loaded: not-found" in output or "could not be found" in output:
            continue
        status = 'FALHA'
        for line in output.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith("Active:") and "active (running)" in stripped_line:
                status = 'NORMAL'
                break
        if status == 'NORMAL':
            details, priority = f'O serviço {service} está ativo e rodando.', 'P4 (Informativa)'
        else:
            details_lines = "\n".join(output.splitlines()[-5:])
            details = f'O serviço {service} está inativo ou em estado de falha.\nDetalhes:\n{details_lines}'
            priority = 'P1 (Crítica)'
        results.append({'category': 'Serviços Essenciais', 'item': f'Serviço: {service}', 'status': status, 'priority': priority, 'details': details})
    return results

def check_disk_health(disks_to_check):
    """Verifica a saúde dos discos físicos fornecidos via linha de comando usando S.M.A.R.T."""
    _, code = run_command("smartctl -V")
    if code != 0:
        return [{'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': 'Ferramenta smartctl', 'status': 'FALHA', 'priority': 'P3 (Média)', 'details': 'A ferramenta smartctl não foi encontrada.'}]
    
    results = []
    for disk_arg in disks_to_check:
        device_path, device_type_arg = disk_arg, ""
        if ':' in disk_arg:
            try:
                device_path, device_type = disk_arg.split(':', 1)
                device_type_arg = f"-d {device_type}"
            except ValueError:
                results.append({'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': f'Argumento Inválido ({disk_arg})', 'status': 'FALHA', 'priority': 'P3 (Média)', 'details': 'Formato incorreto. Use "DISCO" ou "DISCO:TIPO".'})
                continue
        
        smart_output, smart_code = run_command(f"LC_ALL=C smartctl -H {device_type_arg} {device_path}")
        status, priority, details = 'FALHA', 'P2 (Alta)', f"Não foi possível determinar o estado S.M.A.R.T. para {device_path}.\nSaída:\n{smart_output}"

        if "SMART overall-health self-assessment test result: PASSED" in smart_output:
            status, priority, details = 'NORMAL', 'P4 (Informativa)', 'O teste de autoavaliação S.M.A.R.T. foi aprovado.'
        elif "SMART overall-health self-assessment test result: FAILED" in smart_output:
            status, priority, details = 'FALHA', 'P1 (Crítica)', 'O teste de autoavaliação S.M.A.R.T. FALHOU. Recomenda-se a substituição do disco.'
        
        # ... (mais lógica de análise do smartctl)

        results.append({'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': f'Disco {device_path}', 'status': status, 'priority': priority, 'details': details})
    return results

def find_beegfs_mounts():
    """Encontra dinamicamente os pontos de montagem que começam com /BeeGFS."""
    mounts = []
    output, code = run_command("mount")
    if code == 0:
        for line in output.splitlines():
            if ' on /BeeGFS' in line:
                try:
                    mount_point = line.split(' on ')[1].split(' type ')[0]
                    if mount_point.startswith('/BeeGFS'): mounts.append(mount_point)
                except IndexError: continue
    return mounts

def check_disk_io(): return [] # Implementação omitida por brevidade
def check_beegfs_disk_usage(): return [] # Implementação omitida por brevidade
def check_gpus(): return [] # Implementação omitida por brevidade
def check_network_errors(): return [] # Implementação omitida por brevidade
def check_load_average(): return {} # Implementação omitida por brevidade
def check_zombie_processes(): return {} # Implementação omitida por brevidade
def check_uptime(): return {} # Implementação omitida por brevidade


# --- FUNÇÕES DE SAÍDA E PRINCIPAL ---

def setup_output_files():
    """Cria os diretórios de log/relatório e o cabeçalho do CSV se não existirem."""
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    if not os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'category', 'item', 'status', 'priority', 'details'])

def log_to_csv(all_checks, timestamp):
    """Adiciona os resultados das verificações ao arquivo CSV."""
    with open(CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for check in all_checks:
            writer.writerow([timestamp, check.get('category', 'N/A'), check.get('item', 'N/A'), check.get('status', 'N/A'), check.get('priority', 'N/A'), check.get('details', 'N/A')])

def generate_html_report(all_checks, timestamp, hostname, knowledge_base):
    """Gera um relatório HTML com base nos resultados e em um template externo."""
    try:
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            template = f.read()
    except FileNotFoundError:
        print(f"ERRO: Arquivo de template '{TEMPLATE_FILE}' não encontrado.")
        return

    content_html = ""
    grouped_checks = {}
    for check in all_checks:
        if not check: continue # Pula entradas vazias ou None
        category = check.get('category', 'Outros')
        if category not in grouped_checks: grouped_checks[category] = []
        grouped_checks[category].append(check)
        
    for category, items in sorted(grouped_checks.items()):
        content_html += f'<div class="category"><h2>{category}</h2>'
        for item in sorted(items, key=lambda x: x.get('item', '')):
            status_map = {'NORMAL': ('✅', '#28a745'), 'ATENÇÃO': ('⚠️', '#ffc107'), 'FALHA': ('❌', '#dc3545')}
            priority_map = {'P1 (Crítica)': ('#721c24', '#f8d7da'), 'P2 (Alta)': ('#856404', '#fff3cd'), 'P3 (Média)': ('#004085', '#cce5ff')}
            icon, color = status_map.get(item.get('status'), ('?', '#6c757d'))
            priority_tag_html, suggestion_html = '', ''
            if item.get('status') != 'NORMAL':
                priority = item.get('priority', 'P3 (Média)')
                p_color, p_bg_color = priority_map.get(priority, ('#6c757d', '#e9ecef'))
                priority_tag_html = f'<span class="priority-tag" style="--p-color: {p_color}; --p-bg-color: {p_bg_color};">{priority}</span>'
            suggestion = get_kb_suggestion(item.get('details', ''), knowledge_base)
            if suggestion:
                 suggestion_html = f'<div class="item-suggestion"><strong>Sugestão:</strong> {suggestion}</div>'
            content_html += f"""
            <div class="item" style="border-left: 5px solid {color};">
                <div class="item-status">{icon}</div>
                <div class="item-content">
                    <div class="item-title">{item.get('item')} - <span style="color: {color}; margin-left: 4px;">{item.get('status')}</span>{priority_tag_html}</div>
                    <div class="item-details">{item.get('details')}</div>{suggestion_html}
                </div>
            </div>"""
        content_html += '</div>'

    final_html = template.replace('{hostname}', hostname).replace('{timestamp}', timestamp).replace('{content}', content_html)
    with open(HTML_REPORT_FILE, 'w', encoding='utf-8') as f: f.write(final_html)
    print(f"Relatório HTML gerado em: {HTML_REPORT_FILE}")

def parse_cli_args():
    """Analisa os argumentos da linha de comando."""
    args = {'test_html': '--test-html' in sys.argv, 'force_html': '--force-html' in sys.argv, 'smart_disks': []}
    if '--smart-disks' in sys.argv:
        try:
            index = sys.argv.index('--smart-disks')
            if len(sys.argv) > index + 1 and not sys.argv[index + 1].startswith('--'):
                args['smart_disks'] = [d.strip() for d in sys.argv[index + 1].split(',') if d.strip()]
        except (IndexError, ValueError): print("AVISO: Argumento --smart-disks requer uma lista de discos.")
    return args

def main():
    """Função principal que orquestra as verificações e a geração de saídas."""
    hostname, _ = run_command("hostname")
    args = parse_cli_args()
    knowledge_base = load_json_file(KB_FILE, "base de conhecimento")
    
    if args['test_html']:
        print("Modo de teste: Gerando relatório HTML de exemplo...")
        setup_output_files()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_checks = load_json_file(TEST_DATA_FILE, "dados de teste")
        generate_html_report(test_checks, timestamp, hostname, knowledge_base)
        print("Relatório de teste gerado com sucesso.")
        return

    print("Iniciando verificação de monitoramento do cluster HPC...")
    setup_output_files()
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    all_checks = []
    cpu_check, mem_check = check_cpu_memory()
    all_checks.extend([cpu_check, mem_check])
    all_checks.append(check_load_average())
    all_checks.extend(check_gpus())
    
    ib_check = check_infiniband()
    if ib_check:
        all_checks.append(ib_check)

    all_checks.extend(check_network_errors())
    all_checks.append(check_system_errors())
    
    if args['smart_disks']:
        all_checks.extend(check_disk_health(args['smart_disks']))

    all_checks.append(check_zombie_processes())
    all_checks.append(check_uptime())
    all_checks.extend(check_services())
    all_checks.extend(check_disk_io())
    all_checks.extend(check_beegfs_disk_usage())
    
    # Filtra quaisquer resultados None que possam ter sido adicionados
    all_checks = [check for check in all_checks if check]

    log_to_csv(all_checks, timestamp)
    print(f"Resultados registrados em: {CSV_LOG_FILE}")
    
    has_issues = any(check.get('status') in ['ATENÇÃO', 'FALHA'] for check in all_checks)
    if has_issues or args['force_html']:
        print("Problemas detectados ou geração forçada. Gerando relatório HTML...")
        generate_html_report(all_checks, timestamp, hostname, knowledge_base)
    else:
        print("Nenhum problema detectado.")
    print("Verificação concluída.")

if __name__ == '__main__':
    main()

