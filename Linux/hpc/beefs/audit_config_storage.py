#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: audit_config_storage
# description..: Audit configuration Storage Performance 
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 6/26/2025
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import re

# --- Cores para o Terminal ---
class TermColors:
    OK = '\033[92m'      # Verde
    WARNING = '\033[93m'   # Amarelo
    PROBLEM = '\033[91m' # Vermelho
    RESET = '\033[0m'     # Reseta cor
    BOLD = '\033[1m'
    HEADER = '\033[95m'

# --- "Padrão Ouro" - As configurações ideais que definimos ---
GOLDEN_STANDARD = {
    # Kernel (sysctl)
    "vm.vfs_cache_pressure": "50",
    "vm.zone_reclaim_mode": "0",
    # Kernel (sysfs)
    "kernel.mm.transparent_hugepage.enabled": "[madvise] never",
    # XFS (Valores em blocos, como visto no xfs_info)
    "xfs_sunit": 128,
    "xfs_swidth": 1024,
    # Mount
    "required_mount_options": ["noatime", "nodiratime", "largeio"],
    "forbidden_mount_options": ["relatime", "atime"],
    # Scheduler
    "scheduler": "mq-deadline"
}


def print_header(text):
    """Imprime um cabeçalho formatado."""
    print(f"\n{TermColors.HEADER}--- {text} ---{TermColors.RESET}")


def check_result(description, current_value, expected_value, is_ok):
    """Formata e imprime o resultado de uma checagem."""
    if is_ok:
        print(f"  [ {TermColors.OK}OK{TermColors.RESET} ] {description}: {TermColors.OK}{current_value}{TermColors.RESET}")
    else:
        print(f"  [ {TermColors.PROBLEM}FALHA{TermColors.RESET} ] {description}: {TermColors.PROBLEM}{current_value}{TermColors.RESET} (Esperado: '{expected_value}')")


def run_command(command_string):
    """Executa um comando no shell usando os.popen e retorna o resultado."""
    try:
        # os.popen retorna um objeto semelhante a um arquivo
        with os.popen(command_string) as pipe:
            # Lemos a saída completa do comando
            output = pipe.read()
        return output.strip()
    except Exception as e:
        print(f"  [ {TermColors.PROBLEM}ERRO{TermColors.RESET} ] Falha ao executar o comando: '{command_string}'. Erro: {e}")
        return None


def check_global_kernel_settings():
    """Verifica parâmetros globais do kernel."""
    print_header("1. Verificando Configurações Globais do Kernel")

    # VFS Cache Pressure
    current_value = run_command("cat /proc/sys/vm/vfs_cache_pressure")
    if current_value is not None:
        expected_value = GOLDEN_STANDARD["vm.vfs_cache_pressure"]
        check_result("vm.vfs_cache_pressure", current_value, expected_value, current_value == expected_value)

    # Zone Reclaim Mode
    current_value = run_command("cat /proc/sys/vm/zone_reclaim_mode")
    if current_value is not None:
        expected_value = GOLDEN_STANDARD["vm.zone_reclaim_mode"]
        check_result("vm.zone_reclaim_mode", current_value, expected_value, current_value == expected_value)

    # Transparent Huge Pages
    current_value = run_command("cat /sys/kernel/mm/transparent_hugepage/enabled")
    if current_value is not None:
        # A opção 'always' é a única problemática
        is_ok = "always" not in current_value
        check_result("Transparent Huge Pages", current_value, "diferente de 'always'", is_ok)


def check_volumes():
    """Encontra todos os volumes STG/OBJ e verifica cada um."""
    print_header("2. Verificando Volumes de Storage Montados")
    
    mount_output = run_command("mount")
    if not mount_output:
        print("  Não foi possível ler as informações de montagem.")
        return

    # Encontra linhas como: /dev/mapper/dev on /mnt/STG/OBJ1 type xfs (rw,noatime...)
    found_volumes = re.findall(r"(/dev/mapper/\S+)\s+on\s+(/mnt/STG/OBJ\d+)\s+type\s+xfs\s+\((.*?)\)", mount_output)

    if not found_volumes:
        print("  Nenhum volume '/mnt/STG/OBJx' encontrado.")
        return
        
    for device_path, mount_point, mount_options_str in found_volumes:
        print(f"\n{TermColors.BOLD}Analisando: {mount_point}{TermColors.RESET}")
        
        # --- Checagem 1: Parâmetros de Formatação (xfs_info) ---
        xfs_output = run_command(f"xfs_info {device_path}")
        if xfs_output:
            match = re.search(r"sunit=(\d+)\s+swidth=(\d+)\s+blks", xfs_output)
            if match:
                current_sunit = int(match.group(1))
                current_swidth = int(match.group(2))
                check_result("Alinhamento (sunit)", current_sunit, GOLDEN_STANDARD["xfs_sunit"], current_sunit == GOLDEN_STANDARD["xfs_sunit"])
                check_result("Alinhamento (swidth)", current_swidth, GOLDEN_STANDARD["xfs_swidth"], current_swidth == GOLDEN_STANDARD["xfs_swidth"])
            else:
                print(f"  [ {TermColors.WARNING}AVISO{TermColors.RESET} ] Não foi possível extrair sunit/swidth para {device_path}")
        
        # --- Checagem 2: Opções de Montagem ---
        current_options = mount_options_str.split(',')
        for option in GOLDEN_STANDARD["required_mount_options"]:
            check_result(f"Opção de montagem '{option}'", "Presente" if option in current_options else "Ausente", "Presente", option in current_options)
        
        for option in GOLDEN_STANDARD["forbidden_mount_options"]:
             check_result(f"Opção de montagem '{option}'", "Ausente" if option not in current_options else "Presente", "Ausente", option not in current_options)
             
        # --- Checagem 3: Agendador de I/O ---
        dm_name = run_command(f"lsblk -no KNAME {device_path}")
        if dm_name:
            scheduler_output = run_command(f"cat /sys/block/{dm_name}/queue/scheduler")
            if scheduler_output:
                 match = re.search(r"\[(\S+)\]", scheduler_output)
                 if match:
                     current_scheduler = match.group(1)
                     check_result("Agendador de I/O", current_scheduler, GOLDEN_STANDARD["scheduler"], current_scheduler == GOLDEN_STANDARD["scheduler"])


if __name__ == "__main__":
    print(f"{TermColors.BOLD}====================================================={TermColors.RESET}")
    print(f"{TermColors.BOLD}  Script de Auditoria de Performance de Storage v1.0.0{TermColors.RESET}")
    print(f"{TermColors.BOLD}====================================================={TermColors.RESET}")

    # Verifica se o script está rodando como root
    if os.geteuid() != 0:
        print(f"\n{TermColors.PROBLEM}ERRO: Este script precisa ser executado com privilégios de root (sudo).{TermColors.RESET}")
        exit(1)

    check_global_kernel_settings()
    check_volumes()
    
    print("\nAuditoria concluída.\n")
