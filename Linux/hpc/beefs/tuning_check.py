#!/usr/bin/env python3
#
# name.........: tuning check
# description..: Check config tuning (Based initial to Metadata BeeGFS)
# author.......: Alan da Silva Alves
# version......: 1.0.1
# date.........: 5/27/2024
# github.......: github.com/treinalinux
# reference....: https://doc.beegfs.io/7.3.3/advanced_topics/metadata_tuning.html
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

#!/usr/bin/env python3
import os
import sys
import re
import argparse

# Dicionário com os caminhos dos arquivos sysctl e seus valores desejados para --apply-defaults e --display-diff
SYSCTL_SETTINGS_DEFAULTS = {
    "/proc/sys/vm/dirty_background_ratio": "5",
    "/proc/sys/vm/dirty_ratio": "15", # Ajustado de 20 para 15 como um padrão mais agressivo para HDDs
    "/proc/sys/vm/vfs_cache_pressure": "50",
    "/proc/sys/vm/min_free_kbytes": "1048576", # Exemplo para 1GB, ajuste conforme a RAM total
    "/proc/sys/vm/zone_reclaim_mode": "0",
    "/sys/kernel/mm/transparent_hugepage/enabled": "madvise",
    "/sys/kernel/mm/transparent_hugepage/defrag": "madvise",
}

# Template para configurações de dispositivos de bloco para --apply-defaults e --display-diff
DEVICE_PARAM_DEFAULTS_TEMPLATE = {
    "scheduler": "mq-deadline",
    "nr_requests": "256", # Aumentado de 128 para um valor um pouco mais robusto
    "read_ahead_kb": "2048", # Aumentado de 128 para 2MB como um bom ponto de partida para HDDs e arquivos grandes
    "max_sectors_kb": "1024" # Aumentado de 256 para 1MB, se o hardware suportar
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
        return None
    except Exception as e:
        print(f"ERRO ao ler {path}: {e}", file=sys.stderr)
        return "ERRO_LEITURA" # Retorna um valor distinto para erro de leitura

def set_value(path, desired_value, is_display_mode=False):
    """Define um novo valor para um arquivo do sistema, se necessário, ou apenas exibe."""
    current_value = get_current_value(path)

    if current_value == "ERRO_LEITURA" and not is_display_mode: # Não tenta setar se houve erro na leitura
        print(f"AVISO: Não foi possível ler o valor atual de {path} devido a erro. Não será alterado.", file=sys.stderr)
        return False
    if current_value is None and not is_display_mode: # Arquivo não encontrado
        print(f"AVISO: Arquivo {path} não encontrado. Não será alterado.", file=sys.stderr)
        return False

    if is_display_mode:
        if current_value is None:
            print(f"{path}: [Arquivo não encontrado]")
        elif current_value == "ERRO_LEITURA":
            print(f"{path}: [Erro ao ler o valor atual]")
        else:
            print(f"{path}: {current_value}")
        return True

    # Modo de configuração
    if str(current_value) != str(desired_value):
        try:
            with open(path, 'w') as f:
                f.write(str(desired_value))
            print(f"Configurado: {path} = {desired_value} (era: {current_value if current_value not in [None, 'ERRO_LEITURA'] else 'N/A ou erro'})")
            return True
        except PermissionError:
            print(f"ERRO: Permissão negada para escrever em {path}. Execute como root.", file=sys.stderr)
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
        set_value(path, None, is_display_mode=True)

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

def display_differences(target_devices):
    print("--- Verificando Sysctl: Apenas Diferenças dos Padrões ---")
    found_sysctl_diff = False
    for path, default_value in SYSCTL_SETTINGS_DEFAULTS.items():
        current_value = get_current_value(path)
        if current_value is None:
            print(f"DIFERENÇA/ERRO: {path} - Padrão: '{default_value}', Atual: [Arquivo não encontrado]")
            found_sysctl_diff = True
        elif current_value == "ERRO_LEITURA":
            print(f"DIFERENÇA/ERRO: {path} - Padrão: '{default_value}', Atual: [Erro ao ler o valor]")
            found_sysctl_diff = True
        elif str(current_value) != str(default_value):
            print(f"DIFERENÇA: {path} - Padrão: '{default_value}', Atual: '{current_value}'")
            found_sysctl_diff = True
    if not found_sysctl_diff:
        print("Nenhuma diferença encontrada para os parâmetros sysctl predefinidos.")

    print("\n--- Verificando Dispositivos: Apenas Diferenças dos Padrões ---")
    if not target_devices:
        print("Nenhum dispositivo especificado via --devices para verificar.")
        return

    overall_device_diff_found = False
    for dev_name in target_devices:
        print(f"\nDispositivo: /dev/{dev_name}")
        if not os.path.exists(f"/sys/block/{dev_name}"):
            print(f"  AVISO: Dispositivo /dev/{dev_name} não encontrado.")
            continue

        device_specific_diff_found = False
        for param_name, default_value in DEVICE_PARAM_DEFAULTS_TEMPLATE.items():
            path = f"/sys/block/{dev_name}/queue/{param_name}"
            current_value = get_current_value(path)
            if current_value is None:
                print(f"  DIFERENÇA/ERRO: {param_name} - Padrão: '{default_value}', Atual: [Arquivo não encontrado]")
                device_specific_diff_found = True
            elif current_value == "ERRO_LEITURA":
                print(f"  DIFERENÇA/ERRO: {param_name} - Padrão: '{default_value}', Atual: [Erro ao ler o valor]")
                device_specific_diff_found = True
            elif str(current_value) != str(default_value):
                print(f"  DIFERENÇA: {param_name} - Padrão: '{default_value}', Atual: '{current_value}'")
                device_specific_diff_found = True
        
        if not device_specific_diff_found:
            print(f"  Nenhuma diferença encontrada para /dev/{dev_name} em relação aos parâmetros de dispositivo predefinidos.")
        else:
            overall_device_diff_found = True
            
    if not overall_device_diff_found and target_devices:
        # Se iteramos por todos os target_devices e nenhum teve diferença individual
        # E a lista de target_devices não estava vazia inicialmente
        all_devices_checked_had_no_diff = True
        for dev_name in target_devices:
            if not os.path.exists(f"/sys/block/{dev_name}"): # Se algum dispositivo não existia, não podemos dizer que todos estavam ok
                all_devices_checked_had_no_diff = False
                break
        if all_devices_checked_had_no_diff:
             print("\nNenhuma diferença encontrada para os parâmetros de dispositivo predefinidos nos dispositivos especificados.")


def apply_default_settings(target_devices):
    if os.geteuid() != 0:
        print("ERRO: --apply-defaults requer privilégios de root.", file=sys.stderr)
        sys.exit(1) # Sai se não for root ao tentar aplicar padrões

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
    group.add_argument("--display-diff", action="store_true",
                       help="Exibe apenas os parâmetros predefinidos cujos valores atuais diferem dos padrões.")
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
                        help="Lista de dispositivos de bloco separados por vírgula (sem /dev/).\nUsado por --display-all, --display-diff e --apply-defaults.\nPadrão: sda,sdb")

    args = parser.parse_args()

    target_devices_list = [dev.strip() for dev in args.devices.split(',') if dev.strip()]

    if not (args.display_all or args.display_diff or args.display_sysctl or args.display_device or
            args.set_sysctl or args.set_device or args.apply_defaults):
        parser.print_help()
        sys.exit(0)

    # Ações de Display
    if args.display_all:
        display_all_settings(target_devices_list)
    elif args.display_diff:
        display_differences(target_devices_list)
    elif args.display_sysctl:
        set_value(args.display_sysctl, None, is_display_mode=True)
    elif args.display_device:
        dev, param = args.display_device
        path = f"/sys/block/{dev}/queue/{param}"
        if not os.path.exists(f"/sys/block/{dev}"):
            print(f"ERRO: Dispositivo /dev/{dev} não encontrado.", file=sys.stderr)
            sys.exit(1)
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
        if not os.path.exists(f"/sys/block/{dev}"):
            print(f"ERRO: Dispositivo /dev/{dev} não encontrado. Não é possível definir o parâmetro.", file=sys.stderr)
            sys.exit(1)
        set_value(path, value)
    elif args.apply_defaults:
        # A verificação de root é feita dentro da função apply_default_settings
        apply_default_settings(target_devices_list)

    if not (args.set_sysctl or args.set_device or args.apply_defaults): # Não imprime rodapé para ações de set
        print("\nLembretes:")
        print("  - Para 'transparent_hugepage', 'madvise' ou 'never' são frequentemente recomendados para HPC.")
        print("  - Para agendadores de I/O em kernels recentes, considere 'mq-deadline', 'kyber', ou 'none' (para NVMes).")
        print("  - Estas configurações (exceto se aplicadas via --apply-defaults por este script) são temporárias e serão perdidas no reboot.")
        print("    Para persistência, use sysctl.conf, udev rules, ou um serviço `tuned`.")

if __name__ == "__main__":
    main()
