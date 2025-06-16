#!/usr/bin/env python3
#
# name.........: backup_hpc
# description..: Backup HPC
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 6/15/2025
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
import os
import json
import shutil
import datetime
import logging
import glob

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Usando /backup/ para evitar conflitos e seguir boas práticas.
BACKUP_BASE_DIR = "/backup/servers"

# Caminho para o arquivo de fatos do Ansible
FACTS_FILE_PATH = "/tmp/facts.json"

# --- MAPEAMENTO DE ARQUIVOS DE CONFIGURAÇÃO E LOGS CRÍTICOS ---
CONFIG_MAP = {
    "system": [
        "/etc/hostname", "/etc/hosts", "/etc/fstab", "/etc/sysctl.conf",
        "/etc/chrony.conf", "/etc/ntp.conf", "/etc/selinux/config", "/etc/yum.repos.d/",
        # Logs de Sistema e Compliance
        "/var/log/messages", "/var/log/secure", "/var/log/dmesg", "/var/log/compliance_hpc.log"
    ],
    "cron": [
        "/etc/crontab",
        "/etc/cron.d/",
        "/var/spool/cron/"
    ],
    "network": [
        "/etc/sysconfig/network", "/etc/sysconfig/network-scripts/", "/etc/iproute2/"
    ],
    "multipath": [
        "/etc/multipath.conf", "/etc/multipath/conf.d/"
    ],
    "nvidia_driver": [
        "/etc/X11/xorg.conf", "/etc/modprobe.d/nvidia.conf", "/etc/modprobe.d/blacklist-nouveau.conf",
        # Log do Xorg
        "/var/log/Xorg.0.log"
    ],
    "dns_server": [
        "/etc/named.conf", "/etc/named/", "/var/named/",
        # Log do BIND
        "/var/log/named/"
    ],
    "dhcp_server": [
        "/etc/dhcp/dhcpd.conf" # Logs geralmente vão para /var/log/messages, já coberto
    ],
    "firewalld": ["/etc/firewalld/"],
    "iptables": ["/etc/sysconfig/iptables", "/etc/sysconfig/ip6tables"],
    "infiniband": [
        "/etc/rdma/", "/etc/sysconfig/network-scripts/ifcfg-ib*",
        "/etc/udev/rules.d/70-persistent-net.rules"
    ],
    "pacemaker": [
        "/etc/corosync/", "/etc/pacemaker/", "/var/lib/pacemaker/cib/",
        # Log do Pacemaker
        "/var/log/pacemaker/pacemaker.log"
    ],
    "beegfs_meta": ["/etc/beegfs/beegfs-meta.conf", "/var/log/beegfs-meta.log"],
    "beegfs_storage": ["/etc/beegfs/beegfs-storage.conf", "/var/log/beegfs-storage.log"],
    "beegfs_management": ["/etc/beegfs/beegfs-mgmtd.conf", "/var/log/beegfs-mgmtd.log"],
    "beegfs_client": ["/etc/beegfs/beegfs-client.conf", "/etc/beegfs/beegfs-mounts.conf", "/var/log/beegfs-client.log"],
    "mariadb": [
        "/etc/my.cnf", "/etc/my.cnf.d/",
        # Log do MariaDB
        "/var/log/mariadb/"
    ],
    "influxdb": ["/etc/influxdb/influxdb.conf"],
    "grafana": ["/etc/grafana/grafana.ini", "/var/lib/grafana/grafana.db"],
    "bright_cluster_manager": ["/cm/local/apps/cmd/etc/"]
}

def load_ansible_facts(file_path):
    if not os.path.exists(file_path):
        logging.error(f"Arquivo de fatos não encontrado em: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            json_start_index = content.find('{')
            if json_start_index == -1: return None
            return json.loads(content[json_start_index:])
    except (json.JSONDecodeError, IOError) as e:
        logging.error(f"Falha ao ler ou analisar o arquivo JSON: {file_path}. Erro: {e}")
        return None

def identify_server_profiles(facts_data):
    if not facts_data or 'ansible_facts' not in facts_data:
        logging.error("O JSON de fatos é inválido ou não contém a chave 'ansible_facts'.")
        return []

    facts = facts_data.get('ansible_facts', {})
    if isinstance(facts, str):
        try: facts = json.loads(facts)
        except json.JSONDecodeError:
            logging.error("O valor de 'ansible_facts' é uma string JSON mal formada.")
            return []
    if not isinstance(facts, dict):
        logging.error("O valor de 'ansible_facts' não é um dicionário válido.")
        return []

    profiles = set()
    
    if facts.get('ansible_os_family') == 'RedHat':
        profiles.add("system")
        profiles.add("network")

    packages = {}
    pkg_mgr_data = facts.get('ansible_pkg_mgr')
    if isinstance(pkg_mgr_data, dict):
        packages = pkg_mgr_data.get('packages', {})
        if not isinstance(packages, dict):
            logging.warning("A chave 'packages' não contém um dicionário. Tratando como vazio.")
            packages = {}
    elif pkg_mgr_data is not None:
        logging.warning("A chave 'ansible_pkg_mgr' não contém um dicionário. Tratando como vazio.")
        
    if not packages:
        logging.warning("A lista de pacotes está vazia ou não foi encontrada. A detecção de perfis será limitada.")
    else:
        package_to_profile_map = {
            'cronie': 'cron', # Pacote do Crontab
            'device-mapper-multipath': 'multipath',
            'nvidia-driver': 'nvidia_driver', 'kmod-nvidia': 'nvidia_driver',
            'bind': 'dns_server', 'dhcp-server': 'dhcp_server',
            'iptables-services': 'iptables', 'firewalld': 'firewalld',
            'pacemaker': 'pacemaker', 'corosync': 'pacemaker',
            'beegfs-mgmtd': 'beegfs_management', 'beegfs-meta': 'beegfs_meta',
            'beegfs-storage': 'beegfs_storage', 'beegfs-client': 'beegfs_client',
            'mariadb-server': 'mariadb', 'influxdb': 'influxdb',
            'grafana': 'grafana', 'cm-admin': 'bright_cluster_manager',
            'cmdaemon': 'bright_cluster_manager'
        }
        for pkg_name, profile_name in package_to_profile_map.items():
            if any(pkg_name in pkg for pkg in packages):
                profiles.add(profile_name)

    if any(iface.startswith('ib') for iface in facts.get('ansible_interfaces', [])):
        profiles.add("infiniband")

    return list(profiles)

def copy_path(src, dst):
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        logging.info(f"Copiado: {src} -> {dst}")
    except FileNotFoundError:
        logging.debug(f"Caminho opcional não encontrado, pulando: {src}")
    except Exception as e:
        logging.error(f"Falha ao copiar {src}: {e}")

def run_backup(backup_dir, profiles, facts):
    hostname = facts.get('ansible_hostname', 'unknown-host')
    logging.info(f"Servidor: {hostname} | Perfis identificados: {', '.join(sorted(list(profiles)))}")
    paths_to_backup = set()

    for profile in profiles:
        for path_pattern in CONFIG_MAP.get(profile, []):
            # Expande wildcards como * para encontrar múltiplos arquivos de log
            expanded_paths = glob.glob(path_pattern)
            if not expanded_paths and '*' not in path_pattern:
                # Se não encontrou nada e não era um wildcard, adiciona o caminho original para a verificação de existência
                paths_to_backup.add(path_pattern)
            else:
                paths_to_backup.update(expanded_paths)

    if not paths_to_backup:
        logging.warning("Nenhum arquivo ou diretório para backup foi identificado com base nos perfis.")
        return

    logging.info(f"Iniciando backup para: {backup_dir}")
    os.makedirs(backup_dir, exist_ok=True)

    for path in sorted(list(paths_to_backup)):
        if os.path.exists(path):
            destination_path = os.path.join(backup_dir, path.lstrip('/'))
            copy_path(path, destination_path)
        else:
            logging.debug(f"Caminho de configuração '{path}' não encontrado no sistema.")
            
    if "pacemaker" in profiles and shutil.which("pcs"):
        cib_backup_file = os.path.join(backup_dir, "pacemaker_cib.xml")
        logging.info("Exportando o CIB do Pacemaker...")
        os.system(f"pcs cluster cib > {cib_backup_file}")
        if os.path.exists(cib_backup_file) and os.path.getsize(cib_backup_file) > 0:
            logging.info(f"CIB do Pacemaker salvo em: {cib_backup_file}")
        else:
            logging.error("Falha ao exportar o CIB do Pacemaker.")

def main():
    logging.info("--- Iniciando Ferramenta de Backup Abrangente ---")
    
    facts_data = load_ansible_facts(FACTS_FILE_PATH)
    if not facts_data:
        logging.critical("Não foi possível carregar os fatos do Ansible. Abortando.")
        return

    server_profiles = identify_server_profiles(facts_data)
    
    if not server_profiles:
        logging.critical("Nenhum perfil pôde ser identificado a partir dos fatos. Verifique o arquivo JSON. Abortando.")
        return

    ansible_facts_dict = facts_data.get('ansible_facts', {})
    if isinstance(ansible_facts_dict, str):
        try: ansible_facts_dict = json.loads(ansible_facts_dict)
        except json.JSONDecodeError:
            logging.critical("Falha ao decodificar 'ansible_facts' como um dicionário. Abortando.")
            return

    hostname = ansible_facts_dict.get('ansible_hostname', 'unknown-host')
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(BACKUP_BASE_DIR, f"{hostname}_{timestamp}")
    
    run_backup(backup_dir, server_profiles, ansible_facts_dict)

    logging.info("--- Backup Concluído ---")
    logging.info(f"Arquivos de backup salvos em: {backup_dir}")

if __name__ == "__main__":
    main()
