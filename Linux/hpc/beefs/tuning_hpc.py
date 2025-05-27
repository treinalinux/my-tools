#!/usr/bin/env python3
#
# name.........: tuning hpc
# description..: tuning hpc
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 5/27/2024
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os # Importar os para os.popen
import shutil
import re
import sys
import platform
# O módulo subprocess não será usado

# --- Configurações Globais e Constantes ---
RHEL_TARGET_VERSION = "8"
CUSTOM_TUNED_PROFILE_NAME = "beegfs-hpc-hdd"
CUSTOM_TUNED_PROFILE_DIR = f"/etc/tuned/{CUSTOM_TUNED_PROFILE_NAME}"
CUSTOM_TUNED_CONF_FILE = f"{CUSTOM_TUNED_PROFILE_DIR}/tuned.conf"
HPC_LIMITS_FILE = "/etc/security/limits.d/99-hpc.conf"
UDEV_HDD_SCHEDULER_RULE_FILE = "/etc/udev/rules.d/60-hdd-scheduler.rules"

BEEGFS_BASE_CONF_DIR = "/etc/beegfs"
BEEGFS_CLIENT_CONF = f"{BEEGFS_BASE_CONF_DIR}/beegfs-client.conf"
BEEGFS_META_CONF = f"{BEEGFS_BASE_CONF_DIR}/beegfs-meta.conf"
BEEGFS_STORAGE_CONF = f"{BEEGFS_BASE_CONF_DIR}/beegfs-storage.conf"
BEEGFS_MGMTD_CONF = f"{BEEGFS_BASE_CONF_DIR}/beegfs-mgmtd.conf"

# --- Funções Auxiliares ---

def print_info(message):
    print(f"[INFO] {message}")

def print_warning(message):
    print(f"[WARN] {message}")

def print_error(message):
    print(f"[ERROR] {message}")

def print_success(message):
    print(f"[SUCCESS] {message}")

def print_status(message, status, expected_status="OK", indent=1):
    prefix = "  " * indent + "- "
    is_ok = False
    if isinstance(status, bool):
        status_str = "OK" if status else "NOT OK"
        if expected_status == "OK": is_ok = status
        else: is_ok = not status
    elif isinstance(expected_status, list): # Lista de valores aceitáveis
        is_ok = str(status) in [str(s) for s in expected_status]
        status_str = str(status)
    elif str(status) == str(expected_status):
        is_ok = True
        status_str = str(status)
    else:
        is_ok = False
        status_str = str(status)

    color_code = "\033[92m" if is_ok else "\033[91m" # Green / Red
    reset_code = "\033[0m"
    print(f"{prefix}{message}: {color_code}{status_str}{reset_code}")
    return is_ok


def run_command(command_list_or_str, capture_output=True):
    """
    Executa um comando do shell usando os.popen().
    Retorna (stdout, popen_error_msg, returncode).
    stdout: Contém a saída padrão do comando (e stderr, devido ao '2>&1').
    popen_error_msg: Mensagem de erro se o próprio os.popen() falhar, ou None.
    returncode: Código de retorno do comando.
    """
    if isinstance(command_list_or_str, list):
        cmd_str = " ".join(command_list_or_str) # Converte lista para string para os.popen
    else:
        cmd_str = command_list_or_str

    # Mescla stderr com stdout para captura via os.popen,
    # já que os.popen não separa stderr facilmente.
    cmd_to_execute = f"{cmd_str} 2>&1"

    stdout_data = ""
    popen_error_msg = None # Erros específicos da execução do os.popen
    return_code = 0

    try:
        pipe = os.popen(cmd_to_execute, 'r')
        if capture_output:
            stdout_data = pipe.read().strip()
        # Se capture_output for False, stdout_data permanecerá vazio.
        # A saída do comando ainda é consumida pelo pipe ao fechar.

        exit_status_encoded = pipe.close() # Retorna None para sucesso (0), ou status codificado.

        if exit_status_encoded is None:
            return_code = 0
        else:
            # Em sistemas POSIX (Linux), o código de saída real está nos bits mais altos.
            if os.name == 'posix':
                return_code = exit_status_encoded >> 8
            else:
                # Para outros sistemas (ex: Windows), pode ser o código direto.
                # Focado em RHEL, então comportamento POSIX é o esperado.
                return_code = exit_status_encoded

            if return_code == 127: # "Comando não encontrado" frequentemente resulta em 127 pelo shell
                popen_error_msg = f"Comando '{cmd_str.split()[0]}' provavelmente não encontrado pelo shell (retcode 127)."

    except OSError as e:
        # Esta exceção é levantada se os.popen() em si falha
        # (ex: o executável do comando não é encontrado pelo sistema antes do shell).
        print_error(f"OSError ao executar (os.popen): {cmd_str}")
        print_error(f"  Exceção: {e}")
        # stdout_data pode ter sido parcialmente lido se o erro ocorreu depois
        popen_error_msg = str(e)
        return_code = e.errno if hasattr(e, 'errno') else -1 # Usa errno se disponível
    except Exception as e:
        # Outros erros inesperados durante a execução do os.popen
        print_error(f"Exceção genérica ao executar (os.popen): {cmd_str}")
        print_error(f"  Exceção: {e}")
        popen_error_msg = str(e)
        return_code = -1 # Código de erro genérico para o script

    return stdout_data, popen_error_msg, return_code


def read_file_content(filepath):
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return None
    except IOError as e:
        print_error(f"Erro ao ler o arquivo {filepath}: {e}")
        return None

def write_file_content(filepath, content, backup=True):
    if backup and os.path.exists(filepath):
        try:
            # Use um timestamp mais simples para o nome do backup
            backup_name = f"{filepath}.bak_{int(os.path.getmtime(filepath))}"
            shutil.copy2(filepath, backup_name)
            print_info(f"Backup de {filepath} criado como {backup_name}")
        except Exception as e:
            print_warning(f"Não foi possível criar backup de {filepath}: {e}")
            if not confirm_action(f"Continuar sem backup para {filepath}?"):
                return False
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        print_success(f"Arquivo {filepath} atualizado.")
        return True
    except IOError as e:
        print_error(f"Erro ao escrever no arquivo {filepath}: {e}")
        return False

def confirm_action(prompt_message):
    while True:
        reply = input(f"{prompt_message} [s/N]: ").lower().strip()
        if reply == 's':
            return True
        elif reply == 'n' or reply == '':
            return False
        else:
            print_warning("Resposta inválida. Por favor, digite 's' ou 'n'.")

def check_sudo():
    return os.geteuid() == 0

# --- Funções de Verificação ---

def verify_rhel_version():
    print_info("Verificando versão do RHEL...")
    try:
        with open("/etc/redhat-release", "r") as f:
            release_info = f.read()
        version_match = re.search(r"release (\d+)\.?(\d*)", release_info)
        if version_match:
            major_version = version_match.group(1)
            print_status("Versão do RHEL", major_version, RHEL_TARGET_VERSION)
            if major_version != RHEL_TARGET_VERSION:
                print_warning(f"Versão do RHEL ({major_version}) diferente da esperada ({RHEL_TARGET_VERSION}).")
        else:
            print_status("Versão do RHEL", "Não encontrada", RHEL_TARGET_VERSION)
    except FileNotFoundError:
        print_status("Versão do RHEL", "/etc/redhat-release não encontrado", RHEL_TARGET_VERSION)

def verify_tuned_profile():
    print_info("Verificando perfil tuned...")
    stdout, popen_err, retcode = run_command(["tuned-adm", "active"])

    if popen_err:
        print_error(f"Erro ao executar tuned-adm: {popen_err}")
        print_status("Perfil tuned ativo", "Falha ao verificar", CUSTOM_TUNED_PROFILE_NAME)
        return False

    if retcode == 0 and stdout:
        active_profile_match = re.search(r"Current active profile: (.*)", stdout)
        if active_profile_match:
            active_profile = active_profile_match.group(1)
            print_status("Perfil tuned ativo", active_profile, CUSTOM_TUNED_PROFILE_NAME)
            return active_profile == CUSTOM_TUNED_PROFILE_NAME
        else:
            print_warning(f"tuned-adm active retornou saída inesperada: {stdout}")
            print_status("Perfil tuned ativo", "Não foi possível determinar", CUSTOM_TUNED_PROFILE_NAME)
    else:
        print_warning(f"tuned-adm não funcional ou sem perfil ativo (retcode: {retcode}). Saída: {stdout}")
        print_status("Perfil tuned ativo", "tuned-adm falhou ou sem perfil", CUSTOM_TUNED_PROFILE_NAME)
    return False


def verify_kernel_boot_params():
    print_info("Verificando parâmetros de boot do Kernel (via /proc/cmdline)...")
    cmdline = read_file_content("/proc/cmdline")
    if not cmdline:
        print_error("Não foi possível ler /proc/cmdline.")
        return

    expected_params = {
        "transparent_hugepage": ["madvise", "never"],
        "intel_idle.max_cstate": "0",
        "processor.max_cstate": "0",
        "idle": "poll",
        "elevator": "mq-deadline"
    }
    all_found_correctly = True
    for param, expected_val_or_list in expected_params.items():
        found_correct = False
        current_value_str = "Não encontrado"
        param_regex_val = re.search(rf"{re.escape(param)}=(\S+)", cmdline)

        if param_regex_val:
            current_value = param_regex_val.group(1)
            current_value_str = current_value
            if isinstance(expected_val_or_list, list):
                if current_value in expected_val_or_list:
                    found_correct = True
            elif current_value == expected_val_or_list:
                found_correct = True
        
        # Adapta a forma como print_status lida com listas esperadas
        expected_print_val = expected_val_or_list if isinstance(expected_val_or_list, str) else "/".join(expected_val_or_list)

        if not print_status(f"Parâmetro de boot '{param}'", current_value_str, expected_print_val):
            all_found_correctly = False # print_status retorna True se OK
            if not found_correct : # Adiciona warning apenas se realmente não bateu
                 print_warning(f"  Esperado para '{param}': {expected_print_val}, Atual: {current_value_str}")


    if all_found_correctly:
        print_success("Todos os parâmetros de boot verificados parecem corretos em /proc/cmdline.")
    else:
        print_warning("Alguns parâmetros de boot em /proc/cmdline podem precisar de ajuste via GRUB.")
    print_info("Lembre-se: /proc/cmdline mostra os parâmetros da sessão atual. As mudanças no GRUB requerem reboot.")


def verify_resource_limits():
    print_info("Verificando limites de recursos...")
    print_warning("A verificação de ulimit é complexa via script. Verificando a existência e conteúdo do arquivo de configuração.")
    if os.path.exists(HPC_LIMITS_FILE):
        all_ok = print_status(f"Arquivo de limites HPC '{HPC_LIMITS_FILE}'", "Presente", "Presente")
        content = read_file_content(HPC_LIMITS_FILE)
        if content:
            memlock_ok = "unlimited" in content and "memlock" in content
            nofile_ok = ("1048576" in content or "65536" in content) and "nofile" in content # Aceita ambos os valores comuns
            print_status("  memlock unlimited no arquivo", memlock_ok, True)
            print_status("  nofile alto no arquivo", nofile_ok, True)
            if not (memlock_ok and nofile_ok): all_ok = False
        else:
            all_ok = False
    else:
        all_ok = print_status(f"Arquivo de limites HPC '{HPC_LIMITS_FILE}'", "Não encontrado", "Presente")
    return all_ok

def verify_selinux_status():
    print_info("Verificando status do SELinux...")
    selinux_ok_runtime = False
    selinux_ok_config = False

    stdout, popen_err, retcode = run_command(["getenforce"])
    if popen_err:
        print_error(f"Erro ao executar getenforce: {popen_err}")
    elif retcode == 0:
        selinux_status = stdout.strip()
        selinux_ok_runtime = print_status("SELinux status (getenforce)", selinux_status, ["Disabled", "Permissive"])
        if not selinux_ok_runtime:
            print_warning(f"SELinux está {selinux_status}. Para performance máxima, considere 'Disabled' ou 'Permissive'.")
    else:
        print_error(f"Não foi possível obter o status do SELinux via getenforce (retcode: {retcode}, stdout: {stdout}).")

    selinux_config = read_file_content("/etc/selinux/config")
    if selinux_config:
        config_status_match = re.search(r"^\s*SELINUX\s*=\s*(\w+)", selinux_config, re.MULTILINE)
        if config_status_match:
            config_status = config_status_match.group(1).lower() # Lowercase for comparison
            selinux_ok_config = print_status("SELinux config (/etc/selinux/config)", config_status, "disabled")
            if not selinux_ok_config:
                 print_warning(f"  Configuração permanente do SELinux é '{config_status}'. Recomenda-se 'disabled'. Requer reboot.")
        else:
            print_warning("Não foi possível determinar a configuração SELINUX em /etc/selinux/config.")
    else:
        print_warning("Não foi possível ler /etc/selinux/config.")
    return selinux_ok_runtime and selinux_ok_config


def verify_firewall_status():
    print_info("Verificando status do Firewall (firewalld)...")
    firewall_inactive = False
    firewall_disabled_on_boot = False

    # Verifica se está ativo no momento
    # systemctl is-active retorna 3 se inativo
    stdout, popen_err, retcode = run_command("systemctl is-active firewalld")
    if popen_err:
        print_error(f"Erro ao executar systemctl is-active firewalld: {popen_err}")
    elif retcode == 3: # Código para inativo
        firewall_inactive = print_status("Firewalld service (current)", "Inativo", "Inativo")
    elif retcode == 0: # Ativo
        firewall_inactive = print_status("Firewalld service (current)", "Ativo", "Inativo")
        print_warning("Firewalld está ativo. Para performance máxima em rede segura, considere desabilitá-lo.")
    else: # Outro erro ou status
        firewall_inactive = print_status("Firewalld service (current)", f"Status incerto (ret: {retcode}, out: {stdout})", "Inativo")


    # Verifica se está habilitado para iniciar no boot
    # systemctl is-enabled retorna 1 se desabilitado (ou outro erro)
    stdout_en, popen_err_en, retcode_en = run_command("systemctl is-enabled firewalld")
    if popen_err_en:
        print_error(f"Erro ao executar systemctl is-enabled firewalld: {popen_err_en}")
    elif stdout_en == "disabled" or (retcode_en !=0 and stdout_en != "enabled"): # "disabled" ou erro (que não seja "enabled")
        firewall_disabled_on_boot = print_status("Firewalld service (on boot)", "Desabilitado", "Desabilitado")
    elif stdout_en == "enabled":
        firewall_disabled_on_boot = print_status("Firewalld service (on boot)", "Habilitado", "Desabilitado")
        print_warning("  Firewalld está habilitado para iniciar no boot.")
    else:
        firewall_disabled_on_boot = print_status("Firewalld service (on boot)", f"Status incerto (ret: {retcode_en}, out: {stdout_en})", "Desabilitado")
    return firewall_inactive and firewall_disabled_on_boot


def verify_infiniband():
    print_info("Verificando hardware InfiniBand e status RDMA...")
    ib_hw_ok = False
    ib_link_active = False
    beegfs_ib_pkg_ok = False

    stdout, popen_err, retcode = run_command(["ibstat"])
    if popen_err:
        print_error(f"Erro ao executar ibstat: {popen_err}")
    elif retcode == 0 and stdout:
        print_success("ibstat executado com sucesso. Hardware InfiniBand detectado.")
        ib_hw_ok = True
        if "State: Active" in stdout:
            ib_link_active = print_status("Porta InfiniBand Ativa", "Encontrada", "Encontrada")
        else:
            ib_link_active = print_status("Porta InfiniBand Ativa", "Nenhuma encontrada", "Encontrada")
            print_warning("Nenhuma porta InfiniBand parece estar ativa. Verifique cabos e Subnet Manager (opensm).")
    else:
        print_warning(f"Comando ibstat falhou (ret: {retcode}, out: {stdout}) ou não encontrou HCAs. Verifique OFED/rdma-core.")

    stdout_rpm, popen_err_rpm, retcode_rpm = run_command(["rpm", "-q", "libbeegfs-ib"])
    if popen_err_rpm:
        print_error(f"Erro ao executar rpm -q libbeegfs-ib: {popen_err_rpm}")
    elif retcode_rpm == 0 and "libbeegfs-ib" in stdout_rpm:
        beegfs_ib_pkg_ok = print_status("Pacote libbeegfs-ib", "Instalado", "Instalado")
    else:
        beegfs_ib_pkg_ok = print_status("Pacote libbeegfs-ib", "Não instalado", "Instalado")
        print_warning("libbeegfs-ib não encontrado. Necessário para RDMA com BeeGFS.")
    return ib_hw_ok and ib_link_active and beegfs_ib_pkg_ok


def verify_hdd_scheduler(devices_to_check=None):
    print_info("Verificando agendador de I/O para HDDs...")
    if not devices_to_check:
        print_info("  Nenhum dispositivo HDD especificado para verificação do agendador.")
        print_info("  Use --hdd-devices sda,sdb para especificar.")
        return True # Retorna True se não há nada para checar

    all_sched_ok = True
    expected_scheduler = "mq-deadline"
    for device in devices_to_check:
        dev_path = f"/sys/block/{device}/queue/scheduler"
        scheduler_info = read_file_content(dev_path)
        if scheduler_info:
            active_scheduler_match = re.search(r"\[(\w+(?:-\w+)?)\]", scheduler_info)
            current_scheduler = "Não determinado"
            if active_scheduler_match:
                current_scheduler = active_scheduler_match.group(1)
            elif scheduler_info: # Fallback se não houver colchetes
                current_scheduler = scheduler_info.strip().split()[0]
            
            if not print_status(f"Agendador para /dev/{device}", current_scheduler, expected_scheduler):
                all_sched_ok = False
                print_warning(f"  Agendador para /dev/{device} é '{current_scheduler}', esperado '{expected_scheduler}'.")
        else:
            print_warning(f"Não foi possível ler o agendador para /dev/{device} (caminho {dev_path}).")
            all_sched_ok = False

    if os.path.exists(UDEV_HDD_SCHEDULER_RULE_FILE):
        print_status(f"Arquivo de regra udev '{UDEV_HDD_SCHEDULER_RULE_FILE}'", "Presente", "Presente")
    else:
        if not print_status(f"Arquivo de regra udev '{UDEV_HDD_SCHEDULER_RULE_FILE}'", "Não encontrado", "Presente"):
            all_sched_ok = False # Se a regra não existe, não está ok
    return all_sched_ok


def verify_beegfs_conf_value(conf_file_path, key, expected_value, node_type=""):
    if not os.path.exists(conf_file_path):
        return False 

    content = read_file_content(conf_file_path)
    if content is None: return False

    expected_value_str = str(expected_value).lower() if isinstance(expected_value, bool) else str(expected_value)
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(content)
    current_val_str = "Não encontrado/Comentado"
    status_ok = False

    if match:
        current_value = match.group(1).strip()
        current_val_str = current_value
        if isinstance(expected_value, bool): status_ok = current_value.lower() == expected_value_str
        else: status_ok = current_value == expected_value_str
    
    # Usa a lista de valores esperados para print_status se for o caso
    expected_print = [expected_value_str] if not isinstance(expected_value_str, list) else expected_value_str
    print_status(f"{node_type} Conf: '{key}' em {os.path.basename(conf_file_path)}", current_val_str, expected_print, indent=2)
    if not status_ok and current_val_str != "Não encontrado/Comentado":
        print_warning(f"  Valor atual para '{key}' é '{current_val_str}', esperado '{expected_print}'.")
    return status_ok


def verify_beegfs_settings(node_type=None):
    print_info("Verificando configurações do BeeGFS...")
    overall_beegfs_ok = True

    common_settings = { "connRDMAEnabled": "true" }
    client_settings = { "sysMgmtdHost": None } # Presença, valor varia
    storage_settings = { "tuneUseDirectIO": "true" }
    meta_settings = {} # Adicione se necessário

    files_to_check = []
    if node_type == "client" or node_type is None:
        files_to_check.append((BEEGFS_CLIENT_CONF, "Cliente", {**common_settings, **client_settings}))
    if node_type == "storage" or node_type is None:
        files_to_check.append((BEEGFS_STORAGE_CONF, "Storage", {**common_settings, **storage_settings}))
    # ... (meta e mgmtd)

    for conf_file, n_type, settings in files_to_check:
        if not os.path.exists(conf_file):
            if node_type == n_type.lower():
                 print_warning(f"Arquivo de configuração para {n_type} ({conf_file}) não encontrado.")
            continue

        print_info(f"  Verificando {n_type} ({conf_file})...")
        for key, expected in settings.items():
            if expected is None: # Verifica presença
                content = read_file_content(conf_file)
                key_present = False
                if content and re.search(rf"^\s*{re.escape(key)}\s*=", content, re.MULTILINE):
                    key_present = True
                if not print_status(f"{n_type} Conf: '{key}' em {os.path.basename(conf_file)}", "Presente" if key_present else "Não encontrado/Comentado", "Presente", indent=2):
                    overall_beegfs_ok = False
            elif not verify_beegfs_conf_value(conf_file, key, expected, n_type):
                overall_beegfs_ok = False
    return overall_beegfs_ok

# --- Funções de Configuração --- (Requer SUDO e confirmação)

def configure_custom_tuned_profile():
    print_info(f"Configurando perfil tuned customizado '{CUSTOM_TUNED_PROFILE_NAME}'...")
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    # ... (conteúdo do perfil como antes) ...
    profile_content = f"""[main]
summary=Perfil otimizado para BeeGFS HPC com HDDs e InfiniBand (gerado por script)
include=throughput-performance
[cpu]
governor=performance
[vm]
transparent_hugepages=madvise
swappiness=1
dirty_background_ratio=5
dirty_ratio=15
min_free_kbytes=2097152
[sysctl]
vm.zone_reclaim_mode=0
kernel.sched_min_granularity_ns=10000000
kernel.sched_migration_cost_ns=5000000
kernel.sched_autogroup_enabled=0
"""
    if not os.path.exists(CUSTOM_TUNED_PROFILE_DIR):
        try: os.makedirs(CUSTOM_TUNED_PROFILE_DIR); print_success(f"Diretório '{CUSTOM_TUNED_PROFILE_DIR}' criado.")
        except OSError as e: print_error(f"Falha ao criar diretório: {e}"); return False
    return write_file_content(CUSTOM_TUNED_CONF_FILE, profile_content)

def apply_tuned_profile(profile_name):
    print_info(f"Tentando aplicar o perfil tuned '{profile_name}'...")
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    if confirm_action(f"Aplicar perfil tuned '{profile_name}'?"):
        stdout, popen_err, retcode = run_command(["tuned-adm", "profile", profile_name])
        if popen_err: print_error(f"Erro ao executar tuned-adm: {popen_err}"); return False
        if retcode == 0: print_success(f"Perfil '{profile_name}' aplicado."); return True
        else: print_error(f"Falha ao aplicar perfil (ret: {retcode}, out: {stdout})"); return False
    return False # Usuário não confirmou

def configure_resource_limits():
    print_info(f"Configurando limites de recursos em '{HPC_LIMITS_FILE}'...")
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    # ... (conteúdo dos limites como antes) ...
    limits_content = """# Limites para HPC e BeeGFS RDMA
* soft   memlock   unlimited
* hard   memlock   unlimited
* soft   nofile    1048576
* hard   nofile    1048576
* soft   stack     unlimited
* hard   stack     unlimited
* soft   nproc     65536
* hard   nproc     65536
"""
    if os.path.exists(HPC_LIMITS_FILE) and not confirm_action(f"Arquivo '{HPC_LIMITS_FILE}' existe. Sobrescrever?"):
        print_info("Configuração de limites abortada."); return False
    if confirm_action(f"Escrever configuração em '{HPC_LIMITS_FILE}'?\n{limits_content}"):
        if write_file_content(HPC_LIMITS_FILE, limits_content):
            print_info("Lembre-se: limites são aplicados no login."); return True
    return False

def configure_selinux_disabled():
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    # ... (lógica de configuração do SELinux como antes, adaptada) ...
    selinux_config_path = "/etc/selinux/config"
    current_config = read_file_content(selinux_config_path)
    target_line = "SELINUX=disabled"
    if current_config and target_line in current_config and not re.search(rf"^\s*#\s*{target_line}", current_config, re.MULTILINE):
        print_info("SELinux já configurado como 'disabled'."); return True
    if confirm_action(f"Configurar SELINUX=disabled em {selinux_config_path}? (Requer reboot)"):
        new_config = re.sub(r"^\s*SELINUX\s*=\s*\w+", target_line, current_config or "SELINUX=enforcing\n", flags=re.MULTILINE, count=1)
        if target_line not in new_config : # Adiciona se não substituiu
            new_config = target_line + "\n" + (current_config or "")
        if write_file_content(selinux_config_path, new_config):
            print_info("SELinux configurado. Para efeito imediato (permissivo): sudo setenforce 0. Reboot necessário."); return True
    return False

def configure_firewall_disabled():
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    if confirm_action("Desabilitar e parar o firewalld?"):
        success_all = True
        for cmd_args in [["systemctl", "stop", "firewalld"], ["systemctl", "disable", "firewalld"]]:
            print_info(f"Executando: {' '.join(cmd_args)}")
            # Para systemctl, não precisamos capturar a saída para o script
            _, popen_err, retcode = run_command(cmd_args, capture_output=False)
            if popen_err: print_error(f"Erro Popen: {popen_err}"); success_all = False; break
            if retcode != 0: print_error(f"Comando falhou (ret: {retcode})"); success_all = False; break
        if success_all: print_success("Firewalld parado e desabilitado."); return True
        else: print_error("Falha ao desabilitar/parar firewalld."); return False
    return False

def configure_hdd_scheduler_udev_rule():
    if not check_sudo(): print_error("Requer privilégios de root (sudo)."); return False
    # ... (conteúdo da regra udev como antes) ...
    rule_content = """ACTION=="add|change", KERNEL=="sd[a-z]", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="mq-deadline"\n"""
    if os.path.exists(UDEV_HDD_SCHEDULER_RULE_FILE) and not confirm_action(f"Arquivo '{UDEV_HDD_SCHEDULER_RULE_FILE}' existe. Sobrescrever?"):
        print_info("Configuração da regra udev abortada."); return False
    if confirm_action(f"Escrever regra udev?\n{rule_content}"):
        if write_file_content(UDEV_HDD_SCHEDULER_RULE_FILE, rule_content):
            print_info("Regra udev escrita. Recarregando udev...")
            _, popen_err_ctl, ret_ctl = run_command(["udevadm", "control", "--reload-rules"])
            _, popen_err_trg, ret_trg = run_command(["udevadm", "trigger"])
            if not popen_err_ctl and ret_ctl == 0 and not popen_err_trg and ret_trg == 0:
                print_success("Regras udev recarregadas."); return True
            else: print_error(f"Falha ao recarregar udev (ctl_err:{popen_err_ctl}, ctl_ret:{ret_ctl}; trg_err:{popen_err_trg}, trg_ret:{ret_trg})")
    return False

def configure_beegfs_file_value(conf_file_path, key, new_value, node_type_display="BeeGFS"):
    if not check_sudo(): print_error(f"Configurar {conf_file_path} requer sudo."); return False
    if not os.path.exists(conf_file_path): print_warning(f"{conf_file_path} não encontrado."); return False
    # ... (lógica de modificação do arquivo BeeGFS como antes, adaptada) ...
    content = read_file_content(conf_file_path)
    if content is None: return False
    new_value_str = str(new_value).lower() if isinstance(new_value, bool) else str(new_value)
    # Regex para encontrar a linha, incluindo se está comentada
    pattern = re.compile(rf"^(#\s*)?({re.escape(key)}\s*=\s*)(.*?)\s*$", re.MULTILINE)
    match = pattern.search(content)
    new_content = content
    made_change = False

    if match:
        current_line, comment_prefix, key_part, current_val_in_file = match.group(0), match.group(1) or "", match.group(2), match.group(3).strip()
        if current_val_in_file.lower() == new_value_str and not comment_prefix:
            print_info(f"  '{key}' já é '{new_value_str}' e ativo em {os.path.basename(conf_file_path)}."); return True
        
        new_line_content = f"{key_part}{new_value_str}" # Remove comentário ao setar
        if confirm_action(f"Em '{os.path.basename(conf_file_path)}', mudar '{key}' de '{current_val_in_file}' (linha: '{current_line.strip()}') para '{new_value_str}'?"):
            new_content = new_content.replace(current_line, new_line_content, 1)
            made_change = True
    else: # Chave não encontrada, adiciona
        if confirm_action(f"Em '{os.path.basename(conf_file_path)}', adicionar '{key} = {new_value_str}'?"):
            new_content = content.rstrip() + f"\n{key} = {new_value_str}\n"
            made_change = True
    
    if made_change:
        if write_file_content(conf_file_path, new_content):
            print_success(f"  '{key}' configurado para '{new_value_str}' em {os.path.basename(conf_file_path)}."); return True
        else: print_error(f"  Falha ao atualizar {conf_file_path} para '{key}'."); return False
    return True # Nenhuma mudança solicitada ou necessária


def configure_beegfs_settings(node_type_arg=None):
    print_info("Configurando BeeGFS (valores selecionados)...")
    if not check_sudo(): print_error("Modificar BeeGFS conf requer sudo."); return
    # ... (lógica de configuração BeeGFS como antes, usando a função configure_beegfs_file_value) ...
    target_configs = []
    common_settings = {"connRDMAEnabled": True}
    client_specific = {"sysMgmtdHost": "YOUR_MGMTD_HOST_HERE"}
    storage_specific = {"tuneUseDirectIO": True}
    
    # Adapte esta lista conforme os arquivos e configurações que deseja gerenciar
    if node_type_arg is None or node_type_arg == "client":
        if os.path.exists(BEEGFS_CLIENT_CONF):
            target_configs.append({"path": BEEGFS_CLIENT_CONF, "display": "Cliente", "settings": {**common_settings, **client_specific}})
    if node_type_arg is None or node_type_arg == "storage":
        if os.path.exists(BEEGFS_STORAGE_CONF):
            target_configs.append({"path": BEEGFS_STORAGE_CONF, "display": "Storage", "settings": {**common_settings, **storage_specific}})
    # Adicione meta e mgmtd se necessário

    for config_job in target_configs:
        print_info(f"Processando {config_job['display']} ({config_job['path']})...")
        for key, value in config_job['settings'].items():
            if key == "sysMgmtdHost" and value == "YOUR_MGMTD_HOST_HERE":
                 print_warning(f"  '{key}' requer configuração manual do host mgmtd em {os.path.basename(config_job['path'])}.")
                 # Adicionar entrada comentada se não existir
                 content = read_file_content(config_job['path'])
                 if content and not re.search(rf"^\s*(#\s*)?{re.escape(key)}\s*=", content, re.MULTILINE):
                     if confirm_action(f"Adicionar lembrete comentado para '{key}'?"):
                         write_file_content(config_job['path'], content.rstrip() + f"\n# {key} = {value}\n", backup=False) # Não faz backup ao adicionar comentário
                 continue
            configure_beegfs_file_value(config_job['path'], key, value, config_job['display'])


def suggest_grub_changes():
    print_info("\n--- Sugestões de Parâmetros de Boot do Kernel (GRUB) ---")
    print_warning("A modificação do GRUB é sensível e deve ser feita com cuidado.")
    # ... (mensagens de sugestão do GRUB como antes) ...
    print_info('  GRUB_CMDLINE_LINUX="... transparent_hugepage=madvise intel_idle.max_cstate=0 processor.max_cstate=0 idle=poll elevator=mq-deadline slab_common.transparent_hugepage=never ..."')
    print_info("Após editar /etc/default/grub, execute:")
    print_info("  sudo grub2-mkconfig -o /boot/grub2/grub.cfg  (BIOS)")
    print_info("  OU")
    print_info("  sudo grub2-mkconfig -o /boot/efi/EFI/redhat/grub.cfg (UEFI)")
    print_info("Reboot é necessário para aplicar as alterações do GRUB.")


# --- Main ---
def main():
    if sys.version_info < (3, 6):
        print_error("Este script requer Python 3.6 ou superior."); sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="Verifica/Configura ambiente HPC RHEL 8 para BeeGFS.")
    # ... (argumentos do parser como antes) ...
    parser.add_argument("--check", action="store_true", help="Apenas verifica o ambiente (padrão).")
    parser.add_argument("--configure", action="store_true", help="Tenta configurar o ambiente interativamente (REQUER SUDO).")
    parser.add_argument("--node-type", choices=["client", "storage", "meta", "mgmtd"], help="Tipo de nó BeeGFS para ações específicas.")
    parser.add_argument("--hdd-devices", type=str, help="HDDs para verificar/configurar agendador (ex: sda,sdb).")
    parser.add_argument("--all-yes", action="store_true", help="Responde 'sim' para todas as confirmações (EXTREMO CUIDADO!).")
    args = parser.parse_args()

    if not args.configure and not args.check: args.check = True # Padrão é verificar

    print_info("Iniciando script de verificação/configuração do ambiente BeeGFS HPC...")
    # ... (informações de data e plataforma como antes) ...
    try:
        date_output, _, _ = run_command(['date']) # Captura a saída da data
        print_info(f"Data/Hora: {date_output}")
    except Exception:
        print_info("Data/Hora: Não foi possível obter.")
    print_info(f"Plataforma: {platform.platform()}")


    global original_confirm_action # Salva a função original
    original_confirm_action = confirm_action
    if args.all_yes and args.configure:
        print_warning("\n!!! ATENÇÃO: MODO --all-yes ATIVADO. SEM CONFIRMAÇÕES. !!!\n")
        # Redefine confirm_action para sempre retornar True
        globals()['confirm_action'] = lambda prompt_message: True
    
    # --- Seção de Verificação ---
    if args.check:
        print_info("\n--- MODO DE VERIFICAÇÃO ---")
        verify_rhel_version()
        verify_tuned_profile()
        verify_kernel_boot_params()
        verify_resource_limits()
        verify_selinux_status()
        verify_firewall_status()
        verify_infiniband()
        hdds = [dev.strip() for dev in args.hdd_devices.split(',')] if args.hdd_devices else []
        verify_hdd_scheduler(devices_to_check=hdds)
        verify_beegfs_settings(node_type=args.node_type)
        print_info("\n--- FIM DAS VERIFICAÇÕES ---")
        if not args.configure: suggest_grub_changes(); print_info("Use --configure para aplicar configurações (requer sudo).")

    # --- Seção de Configuração ---
    if args.configure:
        print_info("\n--- MODO DE CONFIGURAÇÃO ---")
        if not check_sudo(): print_error("Modo de configuração DEVE ser executado com sudo. Saindo."); sys.exit(1)
        configure_custom_tuned_profile()
        apply_tuned_profile(CUSTOM_TUNED_PROFILE_NAME)
        configure_resource_limits()
        hdds_conf = [dev.strip() for dev in args.hdd_devices.split(',')] if args.hdd_devices else []
        if hdds_conf: configure_hdd_scheduler_udev_rule()
        else: print_info("Nenhum HDD especificado, pulando configuração da regra udev do agendador.")
        configure_beegfs_settings(node_type_arg=args.node_type)
        configure_selinux_disabled()
        configure_firewall_disabled()
        print_info("\n--- FIM DAS CONFIGURAÇÕES ---")
        suggest_grub_changes()
        print_warning("Algumas configurações (GRUB, limites) podem requerer reboot ou relogin.")

    if args.all_yes and 'original_confirm_action' in globals(): # Restaura se foi alterada
        globals()['confirm_action'] = original_confirm_action

if __name__ == "__main__":
    main()
