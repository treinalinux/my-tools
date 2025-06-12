#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import argparse
import shutil

# --- Funções de formatação de saída (cores) ---
class Color:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Color.HEADER}{Color.BOLD}--- {text} ---{Color.ENDC}")

def print_ok(text):
    print(f"[{Color.GREEN}OK{Color.ENDC}] {text}")

def print_warning(text):
    print(f"[{Color.YELLOW}AVISO{Color.ENDC}] {Color.YELLOW}{text}{Color.ENDC}")

def print_error(text):
    print(f"[{Color.RED}ERRO{Color.ENDC}] {Color.RED}{text}{Color.ENDC}")

def run_command(command):
    """Executa um comando no shell usando os.popen e retorna a saída."""
    # os.popen não captura stderr por padrão. Redirecionamos stderr para stdout (2>&1).
    full_command = f"{command} 2>&1"
    
    try:
        # os.popen retorna um objeto do tipo 'file'
        with os.popen(full_command) as pipe:
            output = pipe.read()
            # O método close() retorna o status de saída do processo.
            # Retorna None para sucesso (exit code 0) ou o código de status em caso de erro.
            exit_status = pipe.close()

        if exit_status is None:
            # Comando executado com sucesso (exit code 0)
            return output.strip(), None
        else:
            # Comando falhou. O código de saída real está nos bits mais altos.
            exit_code = exit_status >> 8
            error_message = (
                f"Comando falhou com o código de saída {exit_code}.\n"
                f"Saída capturada: {output.strip()}"
            )
            return None, error_message
            
    except Exception as e:
        # Captura outras exceções inesperadas
        return None, str(e)

def check_root():
    """Verifica se o script está sendo executado como root."""
    if os.geteuid() != 0:
        print_error("Este script precisa ser executado com privilégios de root (use 'sudo').")
        sys.exit(1)

def find_device_from_mountpoint(mount_point):
    """Encontra o dispositivo (ex: /dev/sda) a partir do ponto de montagem."""
    if not os.path.ismount(mount_point):
        return None, None
    
    out, err = run_command(f"df {mount_point}")
    if err or not out:
        return None, None
    
    device_path = out.splitlines()[-1].split()[0]
    
    # Converte /dev/sda1 para sda
    device_name = os.path.basename(device_path)
    # Remove dígitos no final para obter o dispositivo físico (ex: sda1 -> sda)
    physical_device = ''.join([i for i in device_name if not i.isdigit()])

    return device_path, physical_device

def analyze_iostat(device):
    """Analisa a saída do iostat para um dispositivo específico."""
    print_header("Análise do iostat (Snapshot de 2 segundos)")
    print("Nota: Esta análise é mais eficaz se o 'mdtest' estiver em execução.")
    
    if not shutil.which("iostat"):
        print_error("Comando 'iostat' não encontrado. Instale o pacote 'sysstat' (sudo dnf install sysstat).")
        return

    iostat_cmd = f"iostat -d -x -k {device} 1 2"
    out, err = run_command(iostat_cmd)
    if err or not out:
        print_error(f"Não foi possível executar iostat: {err}")
        return

    # Pega o último bloco de dados, que contém a média do intervalo
    lines = out.strip().split('\n')
    header = []
    device_line = ""
    for i in range(len(lines) -1, -1, -1):
        if lines[i].startswith('Device'):
            header = lines[i].split()
            device_line = lines[i+1]
            break

    if not header or not device_line:
        print_error("Não foi possível parsear a saída do iostat.")
        return

    stats = dict(zip(header, device_line.split()))
    
    try:
        r_s = float(stats.get('r/s', 0))
        w_s = float(stats.get('w/s', 0))
        iops = r_s + w_s
        await_ms = float(stats.get('await', 0))
        util_pct = float(stats.get('%util', 0))

        print(f"  - IOPS Total (r/s + w/s): {iops:.2f}")
        print(f"  - Latência Média (await): {await_ms:.2f} ms")
        print(f"  - Saturação do Disco (%util): {util_pct:.2f}%")

        if util_pct > 95.0:
            print_warning("O disco está saturado (próximo de 100% de utilização). Este é um forte indicador de gargalo de hardware.")
        if await_ms > 20.0:
            print_warning(f"A latência ({await_ms:.2f}ms) está alta para um ambiente de alta performance, indicando que o disco não consegue acompanhar as requisições.")
    except (ValueError, KeyError) as e:
        print_error(f"Erro ao analisar as métricas do iostat: {e}")


def analyze_mount_options(mount_point):
    """Verifica as opções de montagem do sistema de arquivos."""
    print_header(f"Análise das Opções de Montagem para '{mount_point}'")
    out, err = run_command(f"mount | grep '{mount_point} '")
    if err or not out:
        print_error(f"Não foi possível obter informações de montagem para {mount_point}: {err}")
        return
    
    print(f"Linha de montagem completa: {out}")
    
    if 'noatime' in out or 'nodiratime' in out:
        print_ok("Opção 'noatime' ou 'nodiratime' encontrada. Isso é bom para a performance.")
    else:
        print_warning("A opção 'atime' (padrão) está ativa. Isso degrada severamente a performance de metadados. Adicione 'noatime' ao seu /etc/fstab e remonte o sistema de arquivos.")

def analyze_xfs_info(mount_point):
    """Exibe informações do xfs_info."""
    print_header(f"Análise do xfs_info para '{mount_point}'")
    if not shutil.which("xfs_info"):
        print_error("Comando 'xfs_info' não encontrado. Instale o pacote 'xfsprogs' (sudo dnf install xfsprogs).")
        return
        
    out, err = run_command(f"xfs_info {mount_point}")
    if err or not out:
        print_error(f"Não foi possível executar xfs_info: {err}")
        return
    
    print("Compare os seguintes valores com o seu ambiente de bom desempenho:")
    for line in out.splitlines():
        if "agcount" in line or "logbsize" in line:
            print(f"  - {line.strip()}")

def analyze_scheduler(device_name):
    """Verifica o I/O scheduler do disco."""
    print_header(f"Análise do I/O Scheduler para '{device_name}'")
    try:
        scheduler_path = f"/sys/block/{device_name}/queue/scheduler"
        with open(scheduler_path, 'r') as f:
            scheduler = f.read().strip()
            print(f"Scheduler em uso: {Color.BOLD}{scheduler}{Color.ENDC}")
            if "mq-deadline" in scheduler or "kyber" in scheduler:
                print_ok("Usando um scheduler moderno recomendado para RHEL 8.")
    except FileNotFoundError:
        print_error(f"Não foi possível encontrar o arquivo de scheduler em '{scheduler_path}'.")

def analyze_raid_controller():
    """Tenta detectar ferramentas de RAID e avisa sobre a verificação do cache."""
    print_header("Análise do Controlador RAID/HBA")
    perccli_path = shutil.which("perccli")
    storcli_path = shutil.which("storcli")

    if perccli_path:
        print_ok(f"Utilitário 'perccli' encontrado em: {perccli_path}")
        print_warning("Execute o comando abaixo para verificar a política de cache dos seus discos virtuais:")
        print(f"  sudo {perccli_path} /c0/vall show all | grep 'Cache Policy'")
        print("  -> Procure por 'WB' (WriteBack). Se estiver 'WT' (WriteThrough), a performance será muito menor.")
    elif storcli_path:
        print_ok(f"Utilitário 'storcli' encontrado em: {storcli_path}")
        print_warning("Execute o comando abaixo para verificar a política de cache dos seus discos virtuais:")
        print(f"  sudo {storcli_path} /c0/vall show all | grep 'Cache Policy'")
        print("  -> Procure por 'WB' (WriteBack). Se estiver 'WT' (WriteThrough), a performance será muito menor.")
    else:
        print_warning("Nenhum utilitário de RAID comum (perccli, storcli) encontrado.")
        print("Verifique manualmente a configuração do seu controlador RAID. A política de cache de escrita é um fator CRÍTICO para a performance e deve estar em modo 'Write-Back' (com uma bateria BBU funcional).")


def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        description="Script de Diagnóstico de I/O para RHEL com XFS.",
        epilog="Execute este script com sudo e enquanto a carga de trabalho estiver ativa."
    )
    parser.add_argument("mount_point", help="O ponto de montagem do sistema de arquivos a ser analisado (ex: /superfs).")
    args = parser.parse_args()

    mount_point = args.mount_point
    
    check_root()
    print(f"{Color.BOLD}Iniciando diagnóstico para o ponto de montagem: {mount_point}{Color.ENDC}")
    
    device_path, device_name = find_device_from_mountpoint(mount_point)
    if not device_path:
        print_error(f"Ponto de montagem '{mount_point}' não é válido ou não foi encontrado.")
        sys.exit(1)
    
    print(f"Dispositivo detectado: {device_path} (Físico: {device_name})")

    analyze_iostat(device_name)
    analyze_mount_options(mount_point)
    analyze_xfs_info(mount_point)
    analyze_scheduler(device_name)
    analyze_raid_controller()
    
    print(f"\n{Color.BOLD}Diagnóstico concluído.{Color.ENDC}")
    print("Compare esta saída com a do seu ambiente de alta performance para encontrar as diferenças.")

if __name__ == "__main__":
    main()
