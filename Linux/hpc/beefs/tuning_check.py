#!/usr/bin/env python3
#
# name.........: tuning check
# description..: Check config tuning (Based initial to Metadata BeeGFS)
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 5/27/2024
# github.......: github.com/treinalinux
# reference....: https://doc.beegfs.io/7.3.3/advanced_topics/metadata_tuning.html
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import sys
import re
import argparse

# Dicionário com os caminhos dos arquivos sysctl e seus valores desejados para --apply-defaults
SYSCTL_SETTINGS_DEFAULTS = {
    "/proc/sys/vm/dirty_background_ratio": "5",
    "/proc/sys/vm/dirty_ratio": "20",
    "/proc/sys/vm/vfs_cache_pressure": "50",
    "/proc/sys/vm/min_free_kbytes": "262144",
    "/proc/sys/vm/zone_reclaim_mode": "0", # 0 é geralmente melhor para HPC
    "/sys/kernel/mm/transparent_hugepage/enabled": "madvise", # Alterado de 'always' para 'madvise' como um padrão mais seguro
    "/sys/kernel/mm/transparent_hugepage/defrag": "madvise",  # Alterado de 'always' para 'madvise'
}

# Template para configurações de dispositivos de bloco para --apply-defaults
DEVICE_PARAM_DEFAULTS_TEMPLATE = {
    "scheduler": "mq-deadline", # Para kernels mais recentes, mq-deadline ou kyber
    "nr_requests": "128",
    "read_ahead_kb": "128", # Pode ser aumentado para HDDs, ex: 1024 ou 2048
    "max_sectors_kb": "256" # Pode ser aumentado dependendo do dispositivo
}

def get_current_value(path):
    """Lê o valor atual de um arquivo do sistema."""
    try:
        with open(path, 'r') as f:
            value = f.read().strip()
            # Para transparent_hugepage e scheduler, o valor ativo é marcado com [colchetes]
            if "transparent_hugepage" in path or "scheduler" in path:
                active_match = re.search(r'\[(\w+(?:-\w+)?)\]', value)
                if active_match:
                    return active_match.group(1)
            return value
    except FileNotFoundError:
        # Não é um erro fatal para display, apenas informa que não foi encontrado
        return None
    except Exception as e:
        print(f"ERRO ao ler {path}: {e}", file=sys.stderr)
        return None

def set_value(path, desired_value, is_display_mode=False):
    """Define um novo valor para um arquivo do sistema, se necessário."""
    current_value = get_current_value(path)

    if current_value is None and not is_display_mode:
        print(f"AVISO: Não foi possível ler o valor atual de {path}. Não será alterado.", file=sys.stderr)
        return False
    elif current_value is None and is_display_mode:
        print(f"{path}: [Arquivo não encontrado ou erro na leitura]")
        return False


    if is_display_mode:
        print(f"{path}: {current_value}")
        return True # Indica que a operação de display foi feita

    # Se não estiver no modo display, tenta configurar
    if str(current_value) != str(desired_value):
        try:
            with open(path, 'w') as f:
                f.write(str(desired_value))
            print(f"Configurado: {path} = {desired_value} (era: {current_value})")
            return True
        except PermissionError:
            print(f"ERRO: Permissão negada para escrever em {path}. Execute como root.", file=sys.stderr)
            # Não sai do script inteiro, permite que outras operações (display) continuem
            return False
        except Exception as e:
            print(f"ERRO ao escrever em {path}: {e}", file=sys.stderr)
            return False
    else:
        print(f"Já configurado: {path} = {desired_value}")
        return True

def display_all_settings(target_devices):
    print("--- Valores Atuais dos Parâmetros Sysctl Predefinidos ---")
    for path, _ in SYSCTL_SETTINGS_DEFAULTS.items():
        set_value(path, None, is_display_mode=True) # Passa None como desired_value para display

    print("\n--- Valores Atuais dos Parâmetros de Dispositivo Predefinidos ---")
    if not target_devices:
        print("Nenhum dispositivo especificado via --devices para exibir.")
        return

    for dev_name in target_devices:
        print(f"\nDispositivo: /dev/{dev_name}")
        if not os.path.exists(f"/sys/block/{dev_name}"):
            print(f"  AVISO: Dispositivo /dev/{dev_name} não encontrado.")
            continue
        for param_name, _ in DEVICE_PARAM_DEFAULTS_TEMPLATE.items():
            path = f"/sys/block/{dev_name}/queue/{param_name}"
            set_value(path, None, is_display_mode=True)

def apply_default_settings(target_devices):
    if os.geteuid() != 0:
        print("ERRO: --apply-defaults requer privilégios de root.", file=sys.stderr)
        return

    print("--- Aplicando Configurações Sysctl Padrão ---")
    for path, value in SYSCTL_SETTINGS_DEFAULTS.items():
        set_value(path, value)

    print("\n--- Aplicando Configurações Padrão para Dispositivos de Bloco ---")
    if not target_devices:
        print("AVISO: Nenhum dispositivo especificado via --devices. Nenhuma configuração de dispositivo aplicada.")
        return

    for dev_name in target_devices:
        print(f"\nDispositivo: /dev/{dev_name}")
        if not os.path.exists(f"/sys/block/{dev_name}"):
            print(f"  AVISO: Dispositivo /dev/{dev_name} não encontrado. Pulando.")
            continue
        for param_name, default_value in DEVICE_PARAM_DEFAULTS_TEMPLATE.items():
            path = f"/sys/block/{dev_name}/queue/{param_name}"
            set_value(path, default_value)

def main():
    parser = argparse.ArgumentParser(
        description="Exibe e configura parâmetros de performance do sistema Linux.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--display-all", action="store_true",
                       help="Exibe os valores atuais de todos os parâmetros predefinidos (sysctl e para --devices).")
    group.add_argument("--display-sysctl", metavar="PATH",
                       help="Exibe o valor atual do parâmetro sysctl especificado.\nEx: /proc/sys/vm/dirty_ratio")
    group.add_argument("--display-device", nargs=2, metavar=("DEVICE", "PARAM"),
                       help="Exibe o valor atual de um parâmetro de dispositivo.\nEx: sda scheduler")
    group.add_argument("--set-sysctl", nargs=2, metavar=("PATH", "VALUE"),
                       help="Define um parâmetro sysctl. Requer root.\nEx: /proc/sys/vm/dirty_ratio 20")
    group.add_argument("--set-device", nargs=3, metavar=("DEVICE", "PARAM", "VALUE"),
                       help="Define um parâmetro de dispositivo. Requer root.\nEx: sda scheduler mq-deadline")
    group.add_argument("--apply-defaults", action="store_true",
                       help="Aplica o conjunto predefinido de otimizações para sysctl e para --devices. Requer root.")

    parser.add_argument("--devices", type=str, default="sda,sdb",
                        help="Lista de dispositivos de bloco separados por vírgula (sem /dev/).\nUsado por --display-all e --apply-defaults.\nPadrão: sda,sdb")

    args = parser.parse_args()

    target_devices_list = [dev.strip() for dev in args.devices.split(',') if dev.strip()]

    # Se nenhuma ação principal for especificada, imprime a ajuda
    if not (args.display_all or args.display_sysctl or args.display_device or
            args.set_sysctl or args.set_device or args.apply_defaults):
        parser.print_help()
        sys.exit(0)

    # Ações de Display
    if args.display_all:
        display_all_settings(target_devices_list)
    elif args.display_sysctl:
        set_value(args.display_sysctl, None, is_display_mode=True)
    elif args.display_device:
        dev, param = args.display_device
        path = f"/sys/block/{dev}/queue/{param}"
        set_value(path, None, is_display_mode=True)

    # Ações de Configuração (requerem root)
    elif args.set_sysctl:
        if os.geteuid() != 0:
            print("ERRO: --set-sysctl requer privilégios de root.", file=sys.stderr)
            sys.exit(1)
        path, value = args.set_sysctl
        set_value(path, value)
    elif args.set_device:
        if os.geteuid() != 0:
            print("ERRO: --set-device requer privilégios de root.", file=sys.stderr)
            sys.exit(1)
        dev, param, value = args.set_device
        path = f"/sys/block/{dev}/queue/{param}"
        set_value(path, value)
    elif args.apply_defaults:
        # A verificação de root é feita dentro da função apply_default_settings
        apply_default_settings(target_devices_list)

    print("\nLembretes:")
    print("  - Para 'transparent_hugepage', 'madvise' ou 'never' são frequentemente recomendados para HPC.")
    print("  - Para agendadores de I/O em kernels recentes, considere 'mq-deadline', 'kyber', ou 'none' (para NVMes).")
    print("  - Estas configurações são temporárias e serão perdidas no reboot. Para persistência, use sysctl.conf, udev rules, ou um serviço `tuned`.")

if __name__ == "__main__":
    main()
