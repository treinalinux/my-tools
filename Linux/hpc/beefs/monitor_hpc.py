#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: monitor_hpc
# description..: Monitor HPC
# author.......: Alan da Silva Alves
# version......: 1.0.2
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

# Caminhos para os arquivos de saída
OUTPUT_DIR = os.path.join(os.path.expanduser('~'), 'hpc_monitoring')
CSV_LOG_FILE = os.path.join(OUTPUT_DIR, 'hpc_monitoring_log.csv')
HTML_REPORT_FILE = os.path.join(OUTPUT_DIR, 'hpc_status_report.html')

# Palavras-chave para procurar em logs do sistema (ex: dmesg)
HARDWARE_ERROR_KEYWORDS = ['error', 'fail', 'critical', 'fatal', 'segfault']


# --- FUNÇÕES AUXILIARES ---

def format_bytes(size_kb):
    """Converte kilobytes para um formato legível (KB, MB, GB, TB)."""
    if size_kb == 0:
        return "0 KB"
    size_names = ("KB", "MB", "GB", "TB")
    i = 0
    size = float(size_kb)
    # Convertendo para a próxima unidade se for >= 1024
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f} {size_names[i]}"


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
    # As colunas são: user, nice, system, idle, iowait, irq, softirq, steal
    cpu_times = [int(p) for p in parts[1:9]]
    total_time = sum(cpu_times)
    idle_time = cpu_times[3]  # O quarto valor (índice 3) é o tempo ocioso
    return total_time, idle_time

def check_cpu_memory():
    """Verifica o uso de CPU e memória RAM usando arquivos nativos do /proc."""

    # --- Verificação de CPU ---
    try:
        total1, idle1 = get_cpu_times()
        time.sleep(1)  # Intervalo de 1 segundo para calcular a diferença
        total2, idle2 = get_cpu_times()

        delta_total = total2 - total1
        delta_idle = idle2 - idle1

        # Evita divisão por zero se o tempo não mudou (sistema extremamente ocioso ou virtualizado)
        if delta_total == 0:
            cpu_usage = 0.0
        else:
            cpu_usage = 100.0 * (delta_total - delta_idle) / delta_total

        cpu_status, cpu_msg = get_status_level(cpu_usage, CPU_THRESHOLD_WARN)
        cpu_priority = 'P2 (Alta)' if cpu_status == 'ATENÇÃO' else 'P4 (Informativa)'
    except (IOError, IndexError, ValueError) as e:
        cpu_status = 'FALHA'
        cpu_msg = f"Não foi possível ler as estatísticas de CPU do /proc/stat. Erro: {e}"
        cpu_priority = 'P1 (Crítica)'

    # --- Verificação de Memória ---
    try:
        mem_info = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem_info[parts[0].rstrip(':')] = int(parts[1])

        mem_total = mem_info.get('MemTotal', 0)
        mem_free = mem_info.get('MemFree', 0)
        buffers = mem_info.get('Buffers', 0)
        cached = mem_info.get('Cached', 0)
        sreclaimable = mem_info.get('SReclaimable', 0)

        # Cálculo preciso de memória "realmente" usada, desconsiderando caches recuperáveis
        mem_used = mem_total - mem_free - buffers - cached - sreclaimable

        if mem_total == 0:
            mem_usage = 0.0
        else:
            mem_usage = (mem_used / mem_total) * 100.0

        mem_status, mem_msg = get_status_level(mem_usage, MEM_THRESHOLD_WARN)
        mem_priority = 'P2 (Alta)' if mem_status == 'ATENÇÃO' else 'P4 (Informativa)'
    except (IOError, KeyError, ValueError) as e:
        mem_status = 'FALHA'
        mem_msg = f"Não foi possível ler as estatísticas de memória do /proc/meminfo. Erro: {e}"
        mem_priority = 'P1 (Crítica)'

    return {
        'category': 'Recursos de Sistema',
        'item': 'Uso de CPU',
        'status': cpu_status,
        'priority': cpu_priority,
        'details': cpu_msg
    }, {
        'category': 'Recursos de Sistema',
        'item': 'Uso de Memória',
        'status': mem_status,
        'priority': mem_priority,
        'details': mem_msg
    }

def run_command(command):
    """Executa um comando no shell usando os.popen e retorna a saída e o código de status."""
    # Redireciona stderr para stdout (2>&1) para capturar toda a saída em um só lugar.
    pipe = os.popen(f'{command} 2>&1')
    output = pipe.read().strip()
    exit_status = pipe.close()

    code = 0
    if exit_status is not None:
        # O status de saída é codificado, então usamos as macros WIFEXITED/WEXITSTATUS para obter o código real.
        if os.WIFEXITED(exit_status):
            code = os.WEXITSTATUS(exit_status)
        else:
            code = 1 # Sinaliza um erro não padrão se o comando não saiu normalmente
    
    return output, code


def check_infiniband():
    """Verifica o status dos links InfiniBand e a conexão com o switch."""
    # Primeiro, verifica se as ferramentas IB estão instaladas.
    output, code = run_command("ibstat -V")
    if code != 0:
        return None  # Retorna None para ignorar completamente a verificação.

    # Executa ibstat para obter detalhes da porta.
    output, code = run_command("ibstat")
    if code != 0:
        return {
            'category': 'Rede de Alta Performance',
            'item': 'InfiniBand Status',
            'status': 'FALHA',
            'priority': 'P1 (Crítica)',
            'details': f"Falha ao executar 'ibstat'. Saída: {output}"
        }

    details_list = []
    status = 'NORMAL'
    
    # Análise do ibstat para cada porta
    current_port = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('Port '):
            current_port = line.split(':')[0]
        elif line.startswith('State:'):
            port_state = line.split(':')[1].strip()
            if port_state != 'Active':
                status = 'ATENÇÃO'
            details_list.append(f"{current_port}: Estado: {port_state}")
        elif line.startswith('Physical state:'):
            phys_state = line.split(':')[1].strip()
            if phys_state != 'LinkUp':
                status = 'ATENÇÃO'
            details_list.append(f", Estado Físico: {phys_state}")
        elif line.startswith('Rate:'):
            rate = line.split(':')[1].strip()
            details_list.append(f", Taxa: {rate}")
    
    ib_health_details = "".join(details_list).replace(", ", "\n", 1).strip()
    if not ib_health_details:
        ib_health_details = "Não foi possível extrair detalhes da porta do ibstat."
        status = 'FALHA'

    # Verifica a conexão do switch com ibnetdiscover
    switch_details = "Informação do switch não disponível."
    ibnet_output, ibnet_code = run_command("ibnetdiscover")
    if ibnet_code == 0:
        for line in ibnet_output.splitlines():
            # Procura a linha que conecta o Adaptador de Canal (CA) a um Switch (SW)
            if line.startswith('Ca') and '-> SW' in line:
                try:
                    parts = line.split('->')
                    switch_part = parts[1].strip()
                    # Ex: SW  21 0x... "MF0;switch-guid"
                    switch_info = switch_part.split('"')
                    switch_name = switch_info[1]
                    switch_details = f"Conectado ao Switch: {switch_name}"
                    break # Pega a primeira conexão encontrada
                except IndexError:
                    continue # Ignora linhas mal formatadas

    final_details = f"{ib_health_details}\n{switch_details}"
    
    if status == 'FALHA':
        priority = 'P1 (Crítica)'
    elif status == 'ATENÇÃO':
        priority = 'P2 (Alta)'
    else:
        priority = 'P4 (Informativa)'

    return {
        'category': 'Rede de Alta Performance',
        'item': 'InfiniBand Health & Topology',
        'status': status,
        'priority': priority,
        'details': final_details
    }

def check_system_errors():
    """Verifica o log do kernel (dmesg) em busca de erros de hardware."""
    command = f"dmesg | grep -iE '({'|'.join(HARDWARE_ERROR_KEYWORDS)})'"
    output, code = run_command(command)

    # O código 0 de grep significa que encontrou correspondências.
    if code == 0 and output:
        return {
            'category': 'Hardware e S.O.',
            'item': 'Logs do Kernel (dmesg)',
            'status': 'ATENÇÃO',
            'priority': 'P2 (Alta)',
            'details': f"Encontradas possíveis falhas de hardware ou erros críticos no dmesg:\n{output}"
        }
    return {
        'category': 'Hardware e S.O.',
        'item': 'Logs do Kernel (dmesg)',
        'status': 'NORMAL',
        'priority': 'P4 (Informativa)',
        'details': 'Nenhum erro crítico recente encontrado no dmesg.'
    }


def check_services():
    """Verifica o status dos serviços, ignorando aqueles que não estão instalados."""
    results = []
    for service in SERVICES_TO_CHECK:
        output, _ = run_command(f"systemctl status {service}")

        # Se o serviço não existe, systemctl informa "Loaded: not-found". Ignoramos.
        if "Loaded: not-found" in output or "could not be found" in output:
            continue
        
        status = 'FALHA'  # Padrão é falha, a menos que encontremos "active (running)"
        
        # Verifica a linha "Active:" na saída do comando status
        for line in output.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith("Active:"):
                if "active (running)" in stripped_line:
                    status = 'NORMAL'
                break
        
        if status == 'NORMAL':
            details = f'O serviço {service} está ativo e rodando.'
            priority = 'P4 (Informativa)'
        else:
            # Pega as últimas 5 linhas da saída para dar contexto ao erro.
            details_lines = "\n".join(output.splitlines()[-5:])
            details = f'O serviço {service} está inativo ou em estado de falha.\nDetalhes:\n{details_lines}'
            priority = 'P1 (Crítica)'

        results.append({
            'category': 'Serviços Essenciais',
            'item': f'Serviço: {service}',
            'status': status,
            'priority': priority,
            'details': details
        })
    return results

def check_disk_health():
    """Verifica a saúde dos discos físicos usando S.M.A.R.T., com lógica específica para SSDs."""
    _, code = run_command("smartctl -V")
    if code != 0:
        return []

    output, code = run_command("ls /sys/block")
    if code != 0:
        return [{
            'category': 'Saúde dos Discos (S.M.A.R.T.)',
            'item': 'Listagem de Discos',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': f"Não foi possível listar os dispositivos de bloco. Saída: {output}"
        }]
    
    results = []
    disk_names = [d for d in output.splitlines() if not d.startswith(('loop', 'ram', 'sr'))]

    for disk in disk_names:
        device_path = f"/dev/{disk}"
        smart_output, smart_code = run_command(f"LC_ALL=C smartctl -H {device_path}")

        status = 'FALHA'
        priority = 'P2 (Alta)'
        details = f"Não foi possível determinar o estado S.M.A.R.T. para {device_path}.\nSaída:\n{smart_output}"

        if "SMART overall-health self-assessment test result: PASSED" in smart_output:
            status = 'NORMAL'
            priority = 'P4 (Informativa)'
            details = 'O teste de autoavaliação S.M.A.R.T. foi aprovado.'
        elif "SMART overall-health self-assessment test result: FAILED" in smart_output:
            status = 'FALHA'
            priority = 'P1 (Crítica)'
            details = 'O teste de autoavaliação S.M.A.R.T. FALHOU. Recomenda-se a substituição do disco.'
        elif "SMART support is: Disabled" in smart_output:
            status = 'ATENÇÃO'
            priority = 'P3 (Média)'
            details = 'O suporte a S.M.A.R.T. está desativado neste dispositivo.'
        elif "SMART support is: Unavailable" in smart_output:
            status = 'NORMAL'
            priority = 'P4 (Informativa)'
            details = 'O dispositivo não suporta S.M.A.R.T.'
        elif smart_code != 0:
            status = 'FALHA'
            priority = 'P2 (Alta)'
            details = f"Erro ao executar smartctl para {device_path}. Verifique as permissões.\nSaída:\n{smart_output}"

        # Lógica adicional para SSDs
        is_ssd_output, _ = run_command(f"cat /sys/block/{disk}/queue/rotational")
        if is_ssd_output.strip() == '0' and status == 'NORMAL':
            ssd_warnings = []
            attr_output, _ = run_command(f"LC_ALL=C smartctl -A {device_path}")
            
            for line in attr_output.splitlines():
                try:
                    if "Percentage Used" in line:
                        percentage_used = float(line.split()[-1])
                        if percentage_used >= SSD_PERCENTAGE_USED_THRESHOLD_WARN:
                            ssd_warnings.append(f"Desgaste ({percentage_used}%) excede o limite de {SSD_PERCENTAGE_USED_THRESHOLD_WARN}%.")
                    elif "Temperature_Celsius" in line:
                        temperature = int(line.split()[-1])
                        if temperature >= SSD_TEMPERATURE_THRESHOLD_WARN:
                            ssd_warnings.append(f"Temperatura ({temperature}°C) excede o limite de {SSD_TEMPERATURE_THRESHOLD_WARN}°C.")
                    elif "Critical Warning" in line:
                        crit_warn_val = int(line.split()[-1])
                        if crit_warn_val != 0:
                            ssd_warnings.append(f"Alerta Crítico de hardware S.M.A.R.T. ativo (valor: {crit_warn_val}).")
                except (ValueError, IndexError):
                    continue
            
            if ssd_warnings:
                status = 'ATENÇÃO'
                priority = 'P2 (Alta)'
                details += " " + " ".join(ssd_warnings)

        results.append({
            'category': 'Saúde dos Discos (S.M.A.R.T.)',
            'item': f'Disco {device_path}',
            'status': status,
            'priority': priority,
            'details': details
        })

    return results

def find_beegfs_mounts():
    """Encontra dinamicamente os pontos de montagem que começam com /BeeGFS."""
    mounts = []
    # Usamos o comando 'mount' que é mais confiável para parsing
    output, code = run_command("mount")
    if code != 0:
        return mounts # Retorna lista vazia se o comando falhar

    for line in output.splitlines():
        # Exemplo de linha: /dev/mapper/vg-storage on /BeeGFS/storage type xfs (...)
        if ' on /BeeGFS' in line:
            try:
                # Extrai o ponto de montagem
                mount_point = line.split(' on ')[1].split(' type ')[0]
                if mount_point.startswith('/BeeGFS'):
                    mounts.append(mount_point)
            except IndexError:
                # Linha mal formatada, ignora
                continue
    return mounts

def check_disk_io():
    """Verifica a latência e utilização de I/O para os discos do BeeGFS."""
    beegfs_mounts = find_beegfs_mounts()

    # Verifica se o iostat está disponível
    _, code = run_command("iostat -V")
    if code != 0:
        # iostat não está disponível, então pulamos esta verificação
        return []

    results = []
    if not beegfs_mounts:
        return results

    # Executa iostat para obter estatísticas. 2 amostras com 1 segundo de intervalo.
    # A adição de 'LC_ALL=C' garante que a saída seja em inglês, evitando erros de parse.
    output, code = run_command("LC_ALL=C iostat -dxk 1 2")
    if code != 0:
        return [{
            'category': 'Performance de Disco (I/O)',
            'item': 'Execução do iostat',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': f"Não foi possível executar o iostat. Saída: {output}"
        }]

    try:
        # A saída do iostat tem dois blocos de relatório; queremos o último.
        last_block = output.split('avg-cpu:')[-1]
        lines = last_block.strip().splitlines()

        header_line_index = -1
        for i, line in enumerate(lines):
            # A verificação agora funciona, pois a saída está padronizada em inglês
            if line.strip().startswith('Device'):
                header_line_index = i
                break
        
        if header_line_index == -1:
            raise ValueError("Linha de cabeçalho 'Device' não encontrada na saída do iostat")

        header = lines[header_line_index].split()
        
        # Adapt to different iostat versions. Some have r_await/w_await, others have a single 'await'.
        has_extended_await = 'r_await' in header and 'w_await' in header
        has_simple_await = 'await' in header

        if not has_extended_await and not has_simple_await:
            raise ValueError("Não foram encontradas colunas de latência ('await' ou 'r_await'/'w_await')")

        if has_extended_await:
            r_await_idx = header.index('r_await')
            w_await_idx = header.index('w_await')
        else:  # has_simple_await
            await_idx = header.index('await')
        
        util_idx = header.index('%util')
        
        device_data_lines = lines[header_line_index + 1:]

    except (IndexError, ValueError) as e:
        return [{
            'category': 'Performance de Disco (I/O)',
            'item': 'Análise da saída do iostat',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': f"Não foi possível analisar a saída do iostat: {e}. Saída completa:\n{output}"
        }]

    for mount in beegfs_mounts:
        # Descobre o dispositivo para o ponto de montagem
        df_output, df_code = run_command(f"df {mount}")
        if df_code != 0 or len(df_output.splitlines()) < 2:
            # Ponto de montagem pode não existir neste nó, o que é normal. Apenas ignoramos.
            continue
        
        device_path = df_output.splitlines()[-1].split()[0]
        
        # Tenta obter o nome do kernel do dispositivo (ex: dm-0) que o iostat usa.
        # Isso é crucial para dispositivos LVM ou /dev/mapper.
        # O fallback é usar o nome base do caminho se lsblk falhar.
        lsblk_output, lsblk_code = run_command(f"lsblk -no KNAME {device_path}")
        if lsblk_code == 0 and lsblk_output:
            device_name = lsblk_output.strip()
        else:
            device_name = os.path.basename(device_path)


        device_found_in_stats = False
        for line in device_data_lines:
            stats = line.split()
            if not stats or stats[0] != device_name:
                continue
            
            device_found_in_stats = True
            try:
                io_util = float(stats[util_idx])
                status = 'NORMAL'
                details_list = []

                # Parte 1: Verifica os limites e constrói as mensagens de alerta
                if has_extended_await:
                    r_await = float(stats[r_await_idx])
                    w_await = float(stats[w_await_idx])
                    if r_await >= IO_AWAIT_THRESHOLD_WARN:
                        status = 'ATENÇÃO'
                        details_list.append(f"Latência de leitura de {r_await}ms excede o limite.")
                    if w_await >= IO_AWAIT_THRESHOLD_WARN:
                        status = 'ATENÇÃO'
                        details_list.append(f"Latência de escrita de {w_await}ms excede o limite.")
                else: # has_simple_await
                    io_await = float(stats[await_idx])
                    if io_await >= IO_AWAIT_THRESHOLD_WARN:
                        status = 'ATENÇÃO'
                        details_list.append(f"Latência de {io_await}ms excede o limite.")

                if io_util >= IO_UTIL_THRESHOLD_WARN:
                    status = 'ATENÇÃO'
                    details_list.append(f"Utilização de {io_util}% excede o limite.")

                # Parte 2: Constrói a string final de detalhes
                if status == 'NORMAL':
                    priority = 'P4 (Informativa)'
                    if has_extended_await:
                        details = f"Latência R/W: {r_await}ms/{w_await}ms, Utilização: {io_util}%."
                    else:
                        details = f"Latência: {io_await}ms, Utilização: {io_util}%."
                else:
                    priority = 'P2 (Alta)'
                    details = " ".join(details_list)
                
                results.append({
                    'category': 'Performance de Disco (I/O)',
                    'item': f'Disco {device_name} ({mount})',
                    'status': status,
                    'priority': priority,
                    'details': details
                })

            except (ValueError, IndexError):
                results.append({
                    'category': 'Performance de Disco (I/O)',
                    'item': f'Disco {device_name} ({mount})',
                    'status': 'FALHA',
                    'priority': 'P2 (Alta)',
                    'details': f'Não foi possível extrair as estatísticas de I/O da linha: "{line}"'
                })
            break # Encontrou o dispositivo, vai para o próximo mount
        
        if not device_found_in_stats:
            results.append({
                'category': 'Performance de Disco (I/O)',
                'item': f'Disco {device_name} ({mount})',
                'status': 'ATENÇÃO',
                'priority': 'P3 (Média)',
                'details': f'O dispositivo {device_name}, encontrado para {mount}, não foi localizado na saída do iostat.'
            })

    return results

def check_beegfs_disk_usage():
    """Verifica o uso de disco individual e agregado de todas as partições BeeGFS."""
    beegfs_mounts = find_beegfs_mounts()

    if not beegfs_mounts:
        # Se não houver montagens BeeGFS, não há nada a verificar.
        return [] # Retorna lista vazia para não poluir o relatório.

    total_size_kb = 0
    total_used_kb = 0
    results = []

    for mount in beegfs_mounts:
        # Usamos -k para obter valores consistentes em Kilobytes
        output, code = run_command(f"df -k {mount}")
        if code != 0:
            # Se o comando falhar para uma montagem, ignoramos e continuamos
            continue
        
        try:
            # A segunda linha contém os dados
            line = output.splitlines()[1]
            parts = line.split()
            # As colunas são: Filesystem, 1K-blocks, Used, Available, Use%
            part_size_kb = int(parts[1])
            part_used_kb = int(parts[2])
            part_available_kb = int(parts[3])
            part_usage_percent = float(parts[4].replace('%', ''))
            
            total_size_kb += part_size_kb
            total_used_kb += part_used_kb

            # Relatório individual por partição
            part_status = 'NORMAL'
            part_priority = 'P4 (Informativa)'
            if part_usage_percent >= BEEGFS_USAGE_THRESHOLD_WARN:
                part_status = 'ATENÇÃO'
                part_priority = 'P2 (Alta)'
            
            part_details = (f"Uso: {part_usage_percent:.1f}%. "
                            f"Total: {format_bytes(part_size_kb)}, "
                            f"Usado: {format_bytes(part_used_kb)}, "
                            f"Disponível: {format_bytes(part_available_kb)}.")

            results.append({
                'category': 'Uso de Disco BeeGFS',
                'item': f'Uso da Partição {mount}',
                'status': part_status,
                'priority': part_priority,
                'details': part_details
            })

        except (IndexError, ValueError):
            # Ignora linhas mal formatadas ou erros de conversão
            continue

    if total_size_kb == 0:
        results.append({
            'category': 'Uso de Disco BeeGFS',
            'item': 'Uso Agregado das Partições',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': 'Não foi possível obter informações de uso de nenhuma partição BeeGFS.'
        })
        return results

    # Relatório agregado
    usage_percent = (total_used_kb / total_size_kb) * 100.0
    total_available_kb = total_size_kb - total_used_kb
    
    status = 'NORMAL'
    priority = 'P4 (Informativa)'
    if usage_percent >= BEEGFS_USAGE_THRESHOLD_WARN:
        status = 'ATENÇÃO'
        priority = 'P2 (Alta)'
        
    details = (f"Uso total: {usage_percent:.1f}%. "
               f"Total: {format_bytes(total_size_kb)}, "
               f"Usado: {format_bytes(total_used_kb)}, "
               f"Disponível: {format_bytes(total_available_kb)}.")

    results.append({
        'category': 'Uso de Disco BeeGFS',
        'item': 'Uso Agregado das Partições',
        'status': status,
        'priority': priority,
        'details': details
    })
    
    return results

def check_gpus():
    """Verifica a temperatura, uso e memória das GPUs NVIDIA."""
    _, code = run_command("nvidia-smi -L")
    if code != 0:
        return [] # Retorna lista vazia se nvidia-smi não estiver disponível

    query_command = (
        "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total "
        "--format=csv,noheader,nounits"
    )
    output, code = run_command(query_command)
    if code != 0:
        return [{
            'category': 'Recursos de GPU',
            'item': 'Execução do nvidia-smi',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': f"Não foi possível obter dados das GPUs. Saída:\n{output}"
        }]

    results = []
    for line in output.splitlines():
        try:
            parts = [p.strip() for p in line.split(',')]
            gpu_index, name, temp, util, mem_used, mem_total = parts
            
            temp = float(temp)
            util = float(util)
            mem_used = float(mem_used)
            mem_total = float(mem_total)
            mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0

            status = 'NORMAL'
            warnings = []
            if temp >= GPU_TEMP_THRESHOLD_WARN:
                status = 'ATENÇÃO'
                warnings.append(f"Temp: {temp}°C (Limite: {GPU_TEMP_THRESHOLD_WARN}°C)")
            
            if util >= GPU_UTIL_THRESHOLD_WARN:
                status = 'ATENÇÃO'
                warnings.append(f"Uso: {util}% (Limite: {GPU_UTIL_THRESHOLD_WARN}%)")

            if status == 'NORMAL':
                priority = 'P4 (Informativa)'
                details = f"Temp: {temp}°C, Uso: {util}%, Memória: {mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%)"
            else:
                priority = 'P2 (Alta)'
                details = ", ".join(warnings)

            results.append({
                'category': 'Recursos de GPU',
                'item': f'GPU {gpu_index}: {name}',
                'status': status,
                'priority': priority,
                'details': details
            })
        except (ValueError, IndexError):
            results.append({
                'category': 'Recursos de GPU',
                'item': f'Análise de GPU',
                'status': 'FALHA',
                'priority': 'P2 (Alta)',
                'details': f'Não foi possível analisar a linha de dados da GPU: "{line}"'
            })
    return results

def check_network_errors():
    """Verifica as interfaces de rede por pacotes com erro ou descartados."""
    try:
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()[2:] # Pula as duas linhas de cabeçalho
    except IOError:
        return [{
            'category': 'Saúde da Rede',
            'item': 'Interfaces de Rede',
            'status': 'FALHA',
            'priority': 'P3 (Média)',
            'details': 'Não foi possível ler /proc/net/dev.'
        }]
    
    results = []
    for line in lines:
        try:
            parts = line.split()
            interface = parts[0].strip(':')
            
            # Pula as interfaces na lista de ignorados
            if any(interface.startswith(prefix) for prefix in INTERFACES_TO_IGNORE):
                continue

            # Colunas (Receive): bytes, packets, errs, drop ... (índices 1, 2, 3, 4)
            # Colunas (Transmit): bytes, packets, errs, drop ... (índices 9, 10, 11, 12)
            rx_errs = int(parts[3])
            rx_drop = int(parts[4])
            tx_errs = int(parts[11])
            tx_drop = int(parts[12])

            total_errors = rx_errs + tx_errs
            total_drops = rx_drop + tx_drop

            if total_errors > 0 or total_drops > 0:
                status = 'ATENÇÃO'
                priority = 'P3 (Média)'
                details = f"Erros: {total_errors} (RX:{rx_errs}, TX:{tx_errs}), Descartados: {total_drops} (RX:{rx_drop}, TX:{tx_drop})"
                results.append({
                    'category': 'Saúde da Rede',
                    'item': f'Interface {interface}',
                    'status': status,
                    'priority': priority,
                    'details': details
                })
        except (ValueError, IndexError):
            continue
    
    if not results:
         return [{
            'category': 'Saúde da Rede',
            'item': 'Interfaces de Rede',
            'status': 'NORMAL',
            'priority': 'P4 (Informativa)',
            'details': 'Nenhum erro ou pacote descartado encontrado nas interfaces.'
        }]
         
    return results

def check_load_average():
    """Verifica a média de carga do sistema."""
    try:
        with open('/proc/loadavg', 'r') as f:
            load_1m, load_5m, load_15m = f.read().split()[:3]
        
        nproc_out, nproc_code = run_command("nproc")
        num_cores = int(nproc_out) if nproc_code == 0 else 1

        load_ratio = float(load_1m) / num_cores
        status = 'NORMAL'
        priority = 'P4 (Informativa)'
        details = f"Carga (1m, 5m, 15m): {load_1m}, {load_5m}, {load_15m} em {num_cores} núcleos."

        if load_ratio >= LOAD_AVERAGE_RATIO_WARN:
            status = 'ATENÇÃO'
            priority = 'P2 (Alta)'
            details += f" A carga de 1 minuto ({load_1m}) é alta para o número de núcleos."

        return {
            'category': 'Recursos de Sistema',
            'item': 'Média de Carga (Load Average)',
            'status': status,
            'priority': priority,
            'details': details
        }
    except (IOError, ValueError):
        return {
            'category': 'Recursos de Sistema',
            'item': 'Média de Carga (Load Average)',
            'status': 'FALHA',
            'priority': 'P2 (Alta)',
            'details': 'Não foi possível ler a média de carga de /proc/loadavg.'
        }
        
def check_zombie_processes():
    """Verifica a existência de processos zumbis."""
    output, code = run_command("ps axo stat | grep -c '^Z'")
    
    if code not in [0, 1]: # Grep retorna 1 se não encontrar nada, o que é OK.
        return {
            'category': 'Saúde do S.O.',
            'item': 'Processos Zumbis',
            'status': 'FALHA',
            'priority': 'P3 (Média)',
            'details': f"Falha ao executar o comando para verificar processos zumbis. Saída: {output}"
        }
    
    try:
        zombie_count = int(output)
        status = 'NORMAL'
        priority = 'P4 (Informativa)'
        details = f"Encontrados {zombie_count} processos zumbis."
        
        if zombie_count >= ZOMBIE_PROCESS_THRESHOLD_WARN:
            status = 'ATENÇÃO'
            priority = 'P3 (Média)'
            details += f" O número excede o limite de {ZOMBIE_PROCESS_THRESHOLD_WARN}."
            
        return {
            'category': 'Saúde do S.O.',
            'item': 'Processos Zumbis',
            'status': status,
            'priority': priority,
            'details': details
        }
    except ValueError:
        return {
            'category': 'Saúde do S.O.',
            'item': 'Processos Zumbis',
            'status': 'FALHA',
            'priority': 'P3 (Média)',
            'details': f"Não foi possível converter a contagem de zumbis para número. Saída: '{output}'"
        }

def check_uptime():
    """Verifica se o servidor foi reiniciado nas últimas 24 horas."""
    output, code = run_command("uptime -s")
    if code != 0:
        return {
            'category': 'Saúde do S.O.',
            'item': 'Tempo de Atividade (Uptime)',
            'status': 'FALHA',
            'priority': 'P3 (Média)',
            'details': f'Não foi possível obter o uptime do sistema. Saída: {output}'
        }

    try:
        # O formato de saída do 'uptime -s' é 'YYYY-MM-DD HH:MM:SS'
        boot_time = datetime.datetime.strptime(output, '%Y-%m-%d %H:%M:%S')
        now = datetime.datetime.now()
        uptime_delta = now - boot_time

        # 24 horas em segundos = 24 * 60 * 60 = 86400
        if uptime_delta.total_seconds() < 86400:
            status = 'ATENÇÃO'
            priority = 'P3 (Média)'
            details = f'O servidor foi reiniciado nas últimas 24 horas. Tempo ativo: {str(uptime_delta).split(".")[0]}.'
        else:
            status = 'NORMAL'
            priority = 'P4 (Informativa)'
            details = f'O servidor está ativo há mais de 24 horas. Tempo ativo: {str(uptime_delta).split(".")[0]}.'

        return {
            'category': 'Saúde do S.O.',
            'item': 'Tempo de Atividade (Uptime)',
            'status': status,
            'priority': priority,
            'details': details
        }
    except ValueError:
        return {
            'category': 'Saúde do S.O.',
            'item': 'Tempo de Atividade (Uptime)',
            'status': 'FALHA',
            'priority': 'P3 (Média)',
            'details': f'Não foi possível analisar a data de boot: "{output}"'
        }

# --- FUNÇÕES DE SAÍDA (LOG E RELATÓRIO) ---

def setup_output_files():
    """Cria o diretório e o cabeçalho do CSV se não existirem."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'category', 'item', 'status', 'priority', 'details'])

def log_to_csv(all_checks, timestamp):
    """Adiciona os resultados das verificações ao arquivo CSV."""
    with open(CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for check in all_checks:
            writer.writerow([
                timestamp,
                check.get('category', 'N/A'),
                check.get('item', 'N/A'),
                check.get('status', 'N/A'),
                check.get('priority', 'N/A'),
                check.get('details', 'N/A')
            ])

def generate_html_report(all_checks, timestamp, hostname):
    """Gera um relatório HTML com base nos resultados das verificações."""
    status_map = {
        'NORMAL': {'icon': '✅', 'color': '#28a745'},
        'ATENÇÃO': {'icon': '⚠️', 'color': '#ffc107'},
        'FALHA': {'icon': '❌', 'color': '#dc3545'}
    }
    
    priority_map = {
        'P1 (Crítica)': {'color': '#721c24', 'bg_color': '#f8d7da'},
        'P2 (Alta)':    {'color': '#856404', 'bg_color': '#fff3cd'},
        'P3 (Média)':   {'color': '#004085', 'bg_color': '#cce5ff'},
        'P4 (Informativa)': {'color': '#155724', 'bg_color': '#d4edda'}
    }

    # Agrupa os itens por categoria
    grouped_checks = {}
    for check in all_checks:
        category = check['category']
        if category not in grouped_checks:
            grouped_checks[category] = []
        grouped_checks[category].append(check)

    html_content = """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relatório de Status do Cluster HPC</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; color: #333; }
            .container { max-width: 900px; margin: auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }
            header { background-color: #004a7f; color: white; padding: 20px; text-align: center; }
            header h1 { margin: 0; font-size: 24px; }
            header p { margin: 5px 0 0; opacity: 0.9; }
            .category { margin: 20px; }
            .category h2 { border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 15px; font-size: 20px; color: #004a7f; }
            .item { display: flex; align-items: flex-start; border: 1px solid #ddd; padding: 15px; border-radius: 5px; margin-bottom: 10px; background: #fafafa; }
            .item-status { font-size: 28px; margin-right: 15px; }
            .item-content { flex-grow: 1; }
            .item-title { font-weight: bold; font-size: 16px; display: flex; align-items: center; }
            .item-details { font-size: 14px; color: #666; white-space: pre-wrap; word-wrap: break-word; }
            .priority-tag {
                font-size: 12px;
                font-weight: bold;
                padding: 3px 8px;
                border-radius: 12px;
                margin-left: 10px;
                color: var(--p-color);
                background-color: var(--p-bg-color);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Relatório de Status do Cluster HPC</h1>
                <p>Servidor: """ + hostname + """</p>
                <p>Gerado em: """ + timestamp + """</p>
            </header>
    """

    for category, items in sorted(grouped_checks.items()):
        html_content += f'<div class="category"><h2>{category}</h2>'
        for item in sorted(items, key=lambda x: x['item']):
            status_info = status_map.get(item['status'], {'icon': '?', 'color': '#6c757d'})
            
            priority_tag_html = ''
            if item['status'] != 'NORMAL':
                priority = item.get('priority', 'P3 (Média)')
                priority_info = priority_map.get(priority, {'color': '#6c757d', 'bg_color': '#e9ecef'})
                priority_tag_html = f'<span class="priority-tag" style="--p-color: {priority_info["color"]}; --p-bg-color: {priority_info["bg_color"]};">{priority}</span>'

            html_content += f"""
            <div class="item" style="border-left: 5px solid {status_info['color']};">
                <div class="item-status">{status_info['icon']}</div>
                <div class="item-content">
                    <div class="item-title">
                        {item['item']} - <span style="color: {status_info['color']}; margin-left: 4px;">{item['status']}</span>
                        {priority_tag_html}
                    </div>
                    <div class="item-details">{item['details']}</div>
                </div>
            </div>
            """
        html_content += '</div>'


    html_content += """
        </div>
    </body>
    </html>
    """

    with open(HTML_REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Relatório HTML gerado em: {HTML_REPORT_FILE}")

def generate_test_data():
    """Gera dados de exemplo para o relatório HTML de teste."""
    return [
        {'category': 'Recursos de Sistema', 'item': 'Uso de CPU', 'status': 'NORMAL', 'priority': 'P4 (Informativa)', 'details': 'Uso de 15.2%'},
        {'category': 'Recursos de Sistema', 'item': 'Uso de Memória', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Uso de 88.9% excede o limite de 85.0%'},
        {'category': 'Recursos de Sistema', 'item': 'Média de Carga (Load Average)', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Carga (1m, 5m, 15m): 35.5, 20.1, 15.0 em 16 núcleos. A carga de 1 minuto (35.5) é alta para o número de núcleos.'},
        {'category': 'Recursos de GPU', 'item': 'GPU 0: NVIDIA A100', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Temp: 92.0°C (Limite: 85.0°C)'},
        {'category': 'Recursos de GPU', 'item': 'GPU 1: NVIDIA A100', 'status': 'NORMAL', 'priority': 'P4 (Informativa)', 'details': 'Temp: 65.0°C, Uso: 80.0%, Memória: 10240/40960 MB (25.0%)'},
        {'category': 'Rede de Alta Performance', 'item': 'InfiniBand Health & Topology', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Port 1: Estado: Active\n, Estado Físico: Down\n, Taxa: 40 Gb/s (QDR)\nConectado ao Switch: Mellanox Technologies Aggregation Switch'},
        {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Encontradas possíveis falhas de hardware ou erros críticos no dmesg:\n[  123.456] mce: [Hardware Error]: CPU 0: Machine Check...'},
        {'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': 'Disco /dev/sda', 'status': 'NORMAL', 'priority': 'P4 (Informativa)', 'details': 'O teste de autoavaliação S.M.A.R.T. foi aprovado.'},
        {'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': 'Disco /dev/sdb', 'status': 'FALHA', 'priority': 'P1 (Crítica)', 'details': 'O teste de autoavaliação S.M.A.R.T. FALHOU. Recomenda-se a substituição do disco.'},
        {'category': 'Saúde dos Discos (S.M.A.R.T.)', 'item': 'Disco /dev/nvme0n1', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'O teste de autoavaliação S.M.A.R.T. foi aprovado. Desgaste (90.0%) excede o limite de 85.0%.'},
        {'category': 'Saúde da Rede', 'item': 'Interface eth0', 'status': 'ATENÇÃO', 'priority': 'P3 (Média)', 'details': 'Erros: 102 (RX:102, TX:0), Descartados: 550 (RX:500, TX:50)'},
        {'category': 'Saúde do S.O.', 'item': 'Processos Zumbis', 'status': 'ATENÇÃO', 'priority': 'P3 (Média)', 'details': 'Encontrados 10 processos zumbis. O número excede o limite de 5.'},
        {'category': 'Saúde do S.O.', 'item': 'Tempo de Atividade (Uptime)', 'status': 'ATENÇÃO', 'priority': 'P3 (Média)', 'details': 'O servidor foi reiniciado nas últimas 24 horas. Tempo ativo: 04:32:15.'},
        {'category': 'Serviços Essenciais', 'item': 'Serviço: beegfs-client', 'status': 'NORMAL', 'priority': 'P4 (Informativa)', 'details': 'O serviço beegfs-client está ativo e rodando.'},
        {'category': 'Serviços Essenciais', 'item': 'Serviço: mysql', 'status': 'FALHA', 'priority': 'P1 (Crítica)', 'details': 'O serviço mysql está inativo ou em estado de falha.\nDetalhes:\n...service failed because o control process exited with error code.'},
        {'category': 'Performance de Disco (I/O)', 'item': 'Disco sdb1 (/mnt/BeeGFS/storage)', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Latência de escrita de 65.7ms excede o limite. Utilização de 95.1% excede o limite.'},
        {'category': 'Uso de Disco BeeGFS', 'item': 'Uso da Partição /BeeGFS/storage', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Uso: 96.3%. Total: 8.0 TB, Usado: 7.7 TB, Disponível: 250.0 GB.'},
        {'category': 'Uso de Disco BeeGFS', 'item': 'Uso Agregado das Partições', 'status': 'ATENÇÃO', 'priority': 'P2 (Alta)', 'details': 'Uso total: 92.5%. Total: 10.0 TB, Usado: 9.2 TB, Disponível: 750.0 GB.'}
    ]

# --- FUNÇÃO PRINCIPAL ---

def main():
    """Função principal que orquestra as verificações e a geração de saídas."""
    
    hostname, _ = run_command("hostname")
    
    # Verifica se o modo de teste foi ativado
    if '--test-html' in sys.argv:
        print("Modo de teste: Gerando relatório HTML de exemplo...")
        setup_output_files() # Garante que o diretório de saída existe
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_checks = generate_test_data()
        generate_html_report(test_checks, timestamp, hostname)
        print("Relatório de teste gerado com sucesso.")
        return # Finaliza a execução após gerar o teste

    # Verifica se a geração do relatório HTML deve ser forçada
    force_html_generation = '--force-html' in sys.argv

    print("Iniciando verificação de monitoramento do cluster HPC...")
    setup_output_files()

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Coleta de dados
    all_checks = []
    cpu_check, mem_check = check_cpu_memory()
    all_checks.extend([cpu_check, mem_check])
    all_checks.append(check_load_average())
    all_checks.extend(check_gpus())
    
    # Adiciona a verificação de InfiniBand apenas se ela for aplicável (não retornar None)
    ib_check = check_infiniband()
    if ib_check:
        all_checks.append(ib_check)

    all_checks.extend(check_network_errors())
    all_checks.append(check_system_errors())
    all_checks.extend(check_disk_health())
    all_checks.append(check_zombie_processes())
    all_checks.append(check_uptime())
    all_checks.extend(check_services())
    all_checks.extend(check_disk_io())
    all_checks.extend(check_beegfs_disk_usage())

    # Log para CSV (sempre executa)
    log_to_csv(all_checks, timestamp)
    print(f"Resultados registrados em: {CSV_LOG_FILE}")

    # Verifica se há algum problema
    has_issues = any(check['status'] in ['ATENÇÃO', 'FALHA'] for check in all_checks)

    # Gera o relatório se houver problemas OU se a geração for forçada
    if has_issues or force_html_generation:
        if has_issues:
            print("Problemas detectados. Gerando relatório HTML...")
        else: # A geração foi forçada
            print("Geração de relatório forçada via argumento. Gerando relatório HTML...")
        generate_html_report(all_checks, timestamp, hostname)
    else:
        print("Nenhum problema detectado. O relatório HTML não será gerado.")

    print("Verificação concluída.")


if __name__ == '__main__':
    main()


