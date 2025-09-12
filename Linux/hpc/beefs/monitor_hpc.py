#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: monitor_hpc
# description..: Monitor HPC
# author.......: Alan da Silva Alves
# version......: 1.0.0
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

# Lista de serviços para monitorar (use os nomes exatos dos serviços no systemd)
SERVICES_TO_CHECK = [
    'beegfs-client',  # Exemplo para BeeGFS
    'grafana-server', # Exemplo para Grafana
    'mysql',          # ou 'mariadb'
    'pacemaker',      # ou 'pcsd'
    'cmdaemon'        # Bright Cluster Manager Daemon
]

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
    except (IOError, IndexError, ValueError) as e:
        cpu_status = 'FALHA'
        cpu_msg = f"Não foi possível ler as estatísticas de CPU do /proc/stat. Erro: {e}"

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
    except (IOError, KeyError, ValueError) as e:
        mem_status = 'FALHA'
        mem_msg = f"Não foi possível ler as estatísticas de memória do /proc/meminfo. Erro: {e}"

    return {
        'category': 'Recursos de Sistema',
        'item': 'Uso de CPU',
        'status': cpu_status,
        'details': cpu_msg
    }, {
        'category': 'Recursos de Sistema',
        'item': 'Uso de Memória',
        'status': mem_status,
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
    """Verifica o status dos links InfiniBand, ignorando se a ferramenta não existir."""
    output, code = run_command("ibstat -s")

    # Código 127 é o padrão para "command not found" no shell.
    if code == 127:
        # Retorna None para que esta verificação seja completamente ignorada.
        return None

    if code != 0:
        return {
            'category': 'Rede de Alta Performance',
            'item': 'InfiniBand Status',
            'status': 'FALHA',
            'details': f"Falha ao executar 'ibstat'. Saída: {output}"
        }

    # Análise simples do output.
    if "LinkUp" in output:
        status = 'NORMAL'
        details = 'Todos os links InfiniBand parecem estar ativos (LinkUp).'
    else:
        status = 'ATENÇÃO'
        details = f"Verifique o estado dos links InfiniBand. Resposta do comando:\n{output}"

    return {
        'category': 'Rede de Alta Performance',
        'item': 'InfiniBand Status',
        'status': status,
        'details': details
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
            'details': f"Encontradas possíveis falhas de hardware ou erros críticos no dmesg:\n{output}"
        }
    return {
        'category': 'Hardware e S.O.',
        'item': 'Logs do Kernel (dmesg)',
        'status': 'NORMAL',
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
        else:
            # Pega as últimas 5 linhas da saída para dar contexto ao erro.
            details_lines = "\n".join(output.splitlines()[-5:])
            details = f'O serviço {service} está inativo ou em estado de falha.\nDetalhes:\n{details_lines}'

        results.append({
            'category': 'Serviços Essenciais',
            'item': f'Serviço: {service}',
            'status': status,
            'details': details
        })
    return results

def find_beegfs_mounts():
    """Encontra dinamicamente os pontos de montagem do BeeGFS que começam com /mnt/BeeGFS."""
    mounts = []
    # Usamos o comando 'mount' que é mais confiável para parsing
    output, code = run_command("mount")
    if code != 0:
        return mounts # Retorna lista vazia se o comando falhar

    for line in output.splitlines():
        # Exemplo de linha: /dev/sda1 on /mnt/BeeGFS/storage type xfs (...)
        if ' on /mnt/BeeGFS' in line:
            try:
                # Extrai o ponto de montagem
                mount_point = line.split(' on ')[1].split(' type ')[0]
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
            'details': f"Não foi possível analisar a saída do iostat: {e}. Saída completa:\n{output}"
        }]

    for mount in beegfs_mounts:
        # Descobre o dispositivo para o ponto de montagem
        df_output, df_code = run_command(f"df {mount}")
        if df_code != 0 or len(df_output.splitlines()) < 2:
            # Ponto de montagem pode não existir neste nó, o que é normal. Apenas ignoramos.
            continue
        
        device_path = df_output.splitlines()[-1].split()[0]
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
                    if has_extended_await:
                        details = f"Latência R/W: {r_await}ms/{w_await}ms, Utilização: {io_util}%."
                    else:
                        details = f"Latência: {io_await}ms, Utilização: {io_util}%."
                else:
                    details = " ".join(details_list)
                
                results.append({
                    'category': 'Performance de Disco (I/O)',
                    'item': f'Disco {device_name} ({mount})',
                    'status': status,
                    'details': details
                })

            except (ValueError, IndexError):
                results.append({
                    'category': 'Performance de Disco (I/O)',
                    'item': f'Disco {device_name} ({mount})',
                    'status': 'FALHA',
                    'details': f'Não foi possível extrair as estatísticas de I/O da linha: "{line}"'
                })
            break # Encontrou o dispositivo, vai para o próximo mount
        
        if not device_found_in_stats:
            results.append({
                'category': 'Performance de Disco (I/O)',
                'item': f'Disco {device_name} ({mount})',
                'status': 'ATENÇÃO',
                'details': f'O dispositivo {device_name}, encontrado para {mount}, não foi localizado na saída do iostat.'
            })

    return results

def check_beegfs_disk_usage():
    """Verifica o uso de disco agregado de todas as partições BeeGFS."""
    beegfs_mounts = find_beegfs_mounts()

    if not beegfs_mounts:
        # Se não houver montagens BeeGFS, não há nada a verificar.
        return [] # Retorna lista vazia para não poluir o relatório.

    total_size_kb = 0
    total_used_kb = 0

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
            total_size_kb += int(parts[1])
            total_used_kb += int(parts[2])
        except (IndexError, ValueError):
            # Ignora linhas mal formatadas ou erros de conversão
            continue

    if total_size_kb == 0:
        return [{
            'category': 'Uso de Disco BeeGFS',
            'item': 'Uso Agregado das Partições',
            'status': 'FALHA',
            'details': 'Não foi possível obter informações de uso de nenhuma partição BeeGFS.'
        }]

    usage_percent = (total_used_kb / total_size_kb) * 100.0
    total_available_kb = total_size_kb - total_used_kb
    
    status = 'NORMAL'
    if usage_percent >= BEEGFS_USAGE_THRESHOLD_WARN:
        status = 'ATENÇÃO'
        
    details = (f"Uso total: {usage_percent:.1f}%. "
               f"Total: {format_bytes(total_size_kb)}, "
               f"Usado: {format_bytes(total_used_kb)}, "
               f"Disponível: {format_bytes(total_available_kb)}.")

    return [{
        'category': 'Uso de Disco BeeGFS',
        'item': 'Uso Agregado das Partições',
        'status': status,
        'details': details
    }]


# --- FUNÇÕES DE SAÍDA (LOG E RELATÓRIO) ---

def setup_output_files():
    """Cria o diretório e o cabeçalho do CSV se não existirem."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'category', 'item', 'status', 'details'])

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
                check.get('details', 'N/A')
            ])

def generate_html_report(all_checks, timestamp):
    """Gera um relatório HTML com base nos resultados das verificações."""
    status_map = {
        'NORMAL': {'icon': '✅', 'color': '#28a745'},
        'ATENÇÃO': {'icon': '⚠️', 'color': '#ffc107'},
        'FALHA': {'icon': '❌', 'color': '#dc3545'}
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
            .item-title { font-weight: bold; font-size: 16px; }
            .item-details { font-size: 14px; color: #666; white-space: pre-wrap; word-wrap: break-word; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Relatório de Status do Cluster HPC</h1>
                <p>Gerado em: """ + timestamp + """</p>
            </header>
    """

    for category, items in sorted(grouped_checks.items()):
        html_content += f'<div class="category"><h2>{category}</h2>'
        for item in sorted(items, key=lambda x: x['item']):
            status_info = status_map.get(item['status'], {'icon': '?', 'color': '#6c757d'})
            html_content += f"""
            <div class="item" style="border-left: 5px solid {status_info['color']};">
                <div class="item-status">{status_info['icon']}</div>
                <div class="item-content">
                    <div class="item-title">{item['item']} - <span style="color: {status_info['color']};">{item['status']}</span></div>
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
        {'category': 'Recursos de Sistema', 'item': 'Uso de CPU', 'status': 'NORMAL', 'details': 'Uso de 15.2%'},
        {'category': 'Recursos de Sistema', 'item': 'Uso de Memória', 'status': 'ATENÇÃO', 'details': 'Uso de 88.9% excede o limite de 85.0%'},
        {'category': 'Rede de Alta Performance', 'item': 'InfiniBand Status', 'status': 'NORMAL', 'details': 'Todos os links InfiniBand parecem estar ativos (LinkUp).'},
        {'category': 'Hardware e S.O.', 'item': 'Logs do Kernel (dmesg)', 'status': 'ATENÇÃO', 'details': 'Encontradas possíveis falhas de hardware ou erros críticos no dmesg:\n[  123.456] mce: [Hardware Error]: CPU 0: Machine Check...'},
        {'category': 'Serviços Essenciais', 'item': 'Serviço: beegfs-client', 'status': 'NORMAL', 'details': 'O serviço beegfs-client está ativo e rodando.'},
        {'category': 'Serviços Essenciais', 'item': 'Serviço: mysql', 'status': 'FALHA', 'details': 'O serviço mysql está inativo ou em estado de falha.\nDetalhes:\n...service failed because the control process exited with error code.'},
        {'category': 'Performance de Disco (I/O)', 'item': 'Disco sda1 (/mnt/BeeGFS/meta)', 'status': 'NORMAL', 'details': 'Latência R/W: 5.2ms/8.1ms, Utilização: 25.4%.'},
        {'category': 'Performance de Disco (I/O)', 'item': 'Disco sdb1 (/mnt/BeeGFS/storage)', 'status': 'ATENÇÃO', 'details': 'Latência de escrita de 65.7ms excede o limite. Utilização de 95.1% excede o limite.'},
        {'category': 'Uso de Disco BeeGFS', 'item': 'Uso Agregado das Partições', 'status': 'ATENÇÃO', 'details': 'Uso total: 92.5%. Total: 10.0 TB, Usado: 9.2 TB, Disponível: 750.0 GB.'}
    ]

# --- FUNÇÃO PRINCIPAL ---

def main():
    """Função principal que orquestra as verificações e a geração de saídas."""
    # Verifica se o modo de teste foi ativado
    if '--test-html' in sys.argv:
        print("Modo de teste: Gerando relatório HTML de exemplo...")
        setup_output_files() # Garante que o diretório de saída existe
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_checks = generate_test_data()
        generate_html_report(test_checks, timestamp)
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
    
    # Adiciona a verificação de InfiniBand apenas se ela for aplicável (não retornar None)
    ib_check = check_infiniband()
    if ib_check:
        all_checks.append(ib_check)

    all_checks.append(check_system_errors())
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
        generate_html_report(all_checks, timestamp)
    else:
        print("Nenhum problema detectado. O relatório HTML não será gerado.")

    print("Verificação concluída.")


if __name__ == '__main__':
    main()

