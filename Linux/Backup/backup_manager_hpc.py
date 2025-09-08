#!/usr/bin/env python3
#
# name.........: backup_manager_hpc
# description..: Simple Backup Manager HPC cli
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 8/9/2024
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import sys
import csv
import argparse
import logging
import shlex
from datetime import datetime

# --- Configuração Centralizada de Backups ---
BACKUP_CONFIGS = {
    # Tipos de Serviço
    "beegfs-meta": {"name": "BeeGFS Meta", "paths": ["/etc/beegfs/", "/data/beegfs_meta_logs"]},
    "beegfs-storage": {"name": "BeeGFS Storage", "paths": ["/etc/beegfs/"]},
    "pacemaker": {"name": "Pacemaker/Corosync", "paths": ["/etc/corosync", "/etc/pacemaker"]},
    "bright": {"name": "Bright Cluster Manager", "paths": ["/cm/local/apps/slurm", "/cm/shared/"]},
    "grafana": {"name": "Grafana/InfluxDB", "pre_command": "influxd backup /tmp/influxdb_backup", "paths": ["/etc/grafana", "/tmp/influxdb_backup"]},
    "mysql": {"name": "MySQL/MariaDB", "pre_command": "sudo mysqldump --all-databases > /tmp/all_databases.sql", "paths": ["/tmp/all_databases.sql"]},
    "idrac": {"name": "Dell iDRAC", "pre_command": "sudo racadm scp export -f /tmp/idrac_scp_backup.xml", "paths": ["/tmp/idrac_scp_backup.xml"]},
    "net-bonding": {"name": "Network Bonding", "paths": ["/etc/netplan/", "/etc/sysconfig/network-scripts/", "/etc/network/", "/etc/NetworkManager/system-connections/", "/etc/modprobe.d/"]},
    "network-services": {"name": "Core Network Services", "paths": ["/etc/named.conf", "/etc/named/", "/var/named/", "/etc/dhcp/", "/etc/ntp.conf", "/etc/chrony.conf", "/etc/chrony.keys"]},
    "firewall": {"name": "Firewall", "paths": ["/etc/iptables/", "/etc/sysconfig/iptables", "/etc/firewalld/"]},
    
    # Tipo: Backup de Sistema Otimizado
    "system-full": {
        "name": "Full System (Optimized)", "paths": ["/"], "archive_name_template": "{hostname}_system_full_backup_{timestamp}.tar.gz",
        "exclude_paths": ["/proc/*", "/sys/*", "/dev/*", "/tmp/*", "/var/tmp/*", "/run/*", "/var/run/*", "/mnt/*", "/media/*", "/lost+found", "/var/cache/*", ".cache"]
    }
}


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


def execute_command(command, is_remote=False, hostname=None):
    full_command = command
    if is_remote:
        full_command = "ssh {} {}".format(shlex.quote(hostname), shlex.quote(command + " 2>&1"))
    try:
        pipe = os.popen(full_command)
        output = pipe.read().strip()
        exit_code = pipe.close()
        success = exit_code is None or exit_code == 0
        if not success:
            logging.error("Falha ao executar comando. Código: {}".format(exit_code))
            logging.error("  Comando: {}".format(full_command))
            if output: logging.error("  Saída: {}".format(output))
        return success, output
    except Exception as e:
        logging.error("Exceção inesperada: {}".format(e))
        return False, str(e)


def transfer_and_cleanup(hostname, remote_archive_path, local_dir, dry_run):
    if dry_run:
        logging.info("[DRY-RUN] Transferir '{}' para '{}'.".format(remote_archive_path, local_dir))
        return

    os.makedirs(local_dir, exist_ok=True)
    logging.info("A transferir {} de {}...".format(os.path.basename(remote_archive_path), hostname))
    scp_command = "scp {}:{} {}".format(shlex.quote(hostname), shlex.quote(remote_archive_path), shlex.quote(local_dir))
    success, _ = execute_command(scp_command)
    
    logging.info("A limpar o arquivo temporário em {}...".format(hostname))
    execute_command("rm {}".format(shlex.quote(remote_archive_path)), is_remote=True, hostname=hostname)
    
    if success:
        local_file_path = os.path.join(local_dir, os.path.basename(remote_archive_path))
        logging.info("--> Backup salvo com sucesso em: {}".format(local_file_path))
    else:
        logging.error("--> Falha ao transferir o backup de {}.".format(hostname))

def perform_role_backup(hostname, roles, mode, remote_dir, local_dir, dry_run):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    
    if mode == 'role-agg':
        all_pre_commands, all_paths, all_excludes = [], [], []
        for role in roles:
            config = BACKUP_CONFIGS.get(role, {})
            if "pre_command" in config: all_pre_commands.append(config["pre_command"])
            all_paths.extend(config.get("paths", []))
            all_excludes.extend(config.get("exclude_paths", []))
        if not all_paths: return
        
        logging.info("--- A iniciar Backup Agregado por Papéis para {} ---".format(hostname))
        if dry_run: logging.info("[DRY-RUN] Backup agregado seria executado."); return
        
        for cmd in all_pre_commands: execute_command(str(cmd), is_remote=True, hostname=hostname)
        
        archive_name = "{}_role_agg_backup_{}.tar.gz".format(hostname, timestamp)
        remote_archive_path = os.path.join(remote_dir, archive_name)
        paths_str = " ".join([shlex.quote(p) for p in all_paths])
        exclude_str = " ".join(["--exclude='{}'".format(p) for p in all_excludes])
        backup_command = "sudo tar --ignore-failed-read {} -czf {} {}".format(exclude_str, shlex.quote(remote_archive_path), paths_str)
        
        if execute_command(backup_command, is_remote=True, hostname=hostname)[0]:
            transfer_and_cleanup(hostname, remote_archive_path, os.path.join(local_dir, hostname), dry_run)

    elif mode == 'service':
        for role in roles:
            config = BACKUP_CONFIGS.get(role)
            if not config: continue
            
            logging.info("--- A iniciar Backup por Serviço: {} em {} ---".format(config["name"], hostname))
            if dry_run: logging.info("[DRY-RUN] Backup para '{}' seria executado.".format(config["name"])); continue

            if "pre_command" in config: execute_command(str(config["pre_command"]), is_remote=True, hostname=hostname)
            
            archive_name_template = config.get("archive_name_template", config.get("archive_name", "{}_backup.tar.gz".format(role)))
            archive_name = archive_name_template.format(hostname=hostname, timestamp=timestamp)
            remote_archive_path = os.path.join(remote_dir, archive_name)
            
            paths_str = " ".join([shlex.quote(p) for p in config.get("paths", [])])
            exclude_str = " ".join(["--exclude='{}'".format(p) for p in config.get("exclude_paths", [])])
            backup_command = "sudo tar --ignore-failed-read {} -czf {} {}".format(exclude_str, shlex.quote(remote_archive_path), paths_str)

            if execute_command(backup_command, is_remote=True, hostname=hostname)[0]:
                transfer_and_cleanup(hostname, remote_archive_path, os.path.join(local_dir, hostname), dry_run)


def perform_custom_backup(hostname, paths, remote_dir, local_dir, dry_run):
    logging.info("--- A iniciar Backup Personalizado para {} ---".format(hostname))
    if dry_run:
        logging.info("[DRY-RUN] Backup para os caminhos {} seria executado.".format(', '.join(paths)))
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = "{}_custom_backup_{}.tar.gz".format(hostname, timestamp)
    remote_archive_path = os.path.join(remote_dir, archive_name)
    
    paths_str = " ".join([shlex.quote(p) for p in paths])
    backup_command = "sudo tar --ignore-failed-read -czf {} {}".format(shlex.quote(remote_archive_path), paths_str)
    
    logging.info("A criar arquivo de backup para: {}...".format(paths_str))
    if execute_command(backup_command, is_remote=True, hostname=hostname)[0]:
        transfer_and_cleanup(hostname, remote_archive_path, os.path.join(local_dir, hostname), dry_run)


def perform_restore(hostname, types_to_restore, source_file, dry_run):
    paths_to_restore, names_to_restore = [], []
    is_system_restore = "system-full" in types_to_restore
    is_custom_restore = "custom" in types_to_restore

    if is_custom_restore:
        names_to_restore.append("Ficheiros Personalizados (Conteúdo Completo do Arquivo)")
    else:
        for r_type in types_to_restore:
            config = BACKUP_CONFIGS.get(r_type)
            if config:
                paths_to_restore.extend(config.get("paths", []))
                names_to_restore.append(config["name"])
    
    print("\n" + "="*60)
    print("!! AVISO DE AÇÃO DESTRUTIVA !!")
    if is_system_restore:
        print("!!! RESTAURAÇÃO COMPLETA DO SISTEMA DETETADA !!!")
    print("Você está prestes a RESTAURAR o seguinte em '{}':".format(hostname))
    for name in names_to_restore: print("  - {}".format(name))
    print("Esta ação NÃO PODE ser desfeita.")
    print("="*60)
    
    if dry_run: logging.info("[DRY-RUN] A restauração seria executada."); return

    try: confirm = input("Para confirmar, digite o hostname do anfitrião alvo ({}): ".format(hostname))
    except KeyboardInterrupt: print("\nRestauração cancelada."); sys.exit(1)
    if confirm.strip() != hostname: print("Confirmação inválida. CANCELADO."); sys.exit(1)

    print("Confirmado. A iniciar a restauração...")
    remote_tmp_archive = "/tmp/restore_{}.tar.gz".format(datetime.now().strftime("%Y%m%d%H%M%S"))

    logging.info("A transferir ficheiro de backup...")
    scp_cmd = "scp {} {}:{}".format(shlex.quote(source_file), shlex.quote(hostname), shlex.quote(remote_tmp_archive))
    if not execute_command(scp_cmd)[0]: logging.error("Falha ao transferir. A abortar."); return

    logging.info("A extrair ficheiros...")
    paths_str = "" if (is_custom_restore or is_system_restore) else " ".join([shlex.quote(p) for p in paths_to_restore])
    restore_cmd = "sudo tar --numeric-owner -xzf {} -C / {}".format(shlex.quote(remote_tmp_archive), paths_str)
    if execute_command(restore_cmd, is_remote=True, hostname=hostname)[0]:
        logging.info("Restauração concluída com sucesso.")
    else:
        logging.error("Falha ao extrair ficheiros.")

    logging.info("A limpar ficheiro temporário...")
    execute_command("rm {}".format(shlex.quote(remote_tmp_archive)), is_remote=True, hostname=hostname)


def main():
    setup_logging()

    # --- INÍCIO DA ATUALIZAÇÃO DA DOCUMENTAÇÃO ---
    help_epilog = f"""
---------------------------------
GUIA DE UTILIZAÇÃO E ESTRATÉGIA
---------------------------------

**1. Exemplo de Ficheiro `servers.csv` (para o modo 'backup csv')**

A coluna 'type' pode conter múltiplos papéis, separados por ';'.
Papéis disponíveis: {", ".join(sorted(BACKUP_CONFIGS.keys()))}

Exemplo:
-------------------------------------------------------------------------------------
hostname,type
headnode.cluster.local,system-full;bright;network-services;firewall
db01.cluster.local,system-full;mysql
-------------------------------------------------------------------------------------

**2. Política de Backup: Incremental/Diferencial vs. Full Snapshot**

Este script é otimizado para backups completos (full snapshots) de configurações
e do estado do sistema. Para backups incrementais ou diferenciais eficientes,
especialmente de dados de utilizador com alta rotatividade, o uso de ferramentas
dedicadas como 'Restic' (restic.net) ou 'Borg' é fortemente recomendado. Elas
oferecem deduplicação, encriptação e gestão de snapshots de forma nativa.

Use este script para snapshots de configuração e combine-o com Restic/Borg para
uma estratégia de backup completa e profissional.

**3. Automação com Crontab (Estratégia GFS: Avô-Pai-Filho)**

PRÉ-REQUISITO: É essencial ter autenticação por chave SSH sem password configurada
entre a máquina que executa o script e todos os servidores alvo.

--- Exemplo de Configuração `crontab -e` ---

# (Filho) Backup DIÁRIO de serviços críticos (executa todos os dias às 01:05)
# Use o modo 'service' para backups rápidos e pequenos de configurações.
5 1 * * * /usr/bin/python3 /path/to/backup_manager_hpc.py backup csv /path/to/servers-diario.csv --mode service --local-dir /backups/daily/ >> /var/log/backup_script.log 2>&1

# (Filho) Limpeza de backups diários com mais de 7 dias
10 1 * * * find /backups/daily/ -mtime +7 -exec rm -rf {{}} \\; >> /var/log/backup_script.log 2>&1

# (Pai) Backup SEMANAL completo do sistema (executa todo Domingo às 02:05)
# Use um CSV específico que contenha o papel 'system-full' para os servidores mais críticos.
5 2 * * 0 /usr/bin/python3 /path/to/backup_manager_hpc.py backup csv /path/to/servers-semanal.csv --mode service --local-dir /backups/weekly/ >> /var/log/backup_script.log 2>&1

# (Pai) Limpeza de backups semanais com mais de 35 dias (~5 semanas)
10 2 * * 0 find /backups/weekly/ -mtime +35 -exec rm -rf {{}} \\; >> /var/log/backup_script.log 2>&1

# (Avô) Arquivo MENSAL (executa no primeiro dia do mês às 05:05)
# Recomenda-se um script auxiliar para arquivar o backup semanal mais relevante para um armazenamento de longo prazo.
5 5 1 * * /path/to/archive_monthly_backup.sh >> /var/log/backup_script.log 2>&1
"""
    # --- FIM DA ATUALIZAÇÃO DA DOCUMENTAÇÃO ---

    parser = argparse.ArgumentParser(description="Script para backup e restauração de configurações de servidores.", epilog=help_epilog, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="operation", help="Operação: 'backup' ou 'restore'", required=True)

    # Parser de BACKUP
    parser_b = subparsers.add_parser('backup', help="Executa backups.")
    parser_b.add_argument("--local-dir", default="./backups", help="Diretório local para guardar os backups.")
    parser_b.add_argument("--remote-dir", default="/tmp", help="Diretório temporário no servidor remoto.")
    parser_b.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem executar nenhuma ação.")
    backup_subparsers = parser_b.add_subparsers(dest="backup_type", help="Tipo de backup", required=True)

    parser_b_csv = backup_subparsers.add_parser('csv', help="Executa backups em lote a partir de um ficheiro CSV.")
    parser_b_csv.add_argument("servers_csv", help="Caminho para o ficheiro CSV com os servidores.")
    parser_b_csv.add_argument("--mode", choices=['service', 'role-agg'], default='service', help="Modo: 'service' (um arquivo por papel) ou 'role-agg' (agregado).")

    parser_b_custom = backup_subparsers.add_parser('custom', help="Executa backup de um ficheiro ou diretório específico.")
    parser_b_custom.add_argument("--hostname", required=True, help="O anfitrião onde o backup será executado.")
    parser_b_custom.add_argument("--path", required=True, action='append', help="Caminho a incluir. Pode ser especificado múltiplas vezes.")

    # Parser de RESTORE
    parser_r = subparsers.add_parser('restore', help="Restaura configurações.")
    parser_r.add_argument("--hostname", required=True)
    parser_r.add_argument("--source-file", required=True)
    all_restore_types = list(BACKUP_CONFIGS.keys()) + ['custom']
    parser_r.add_argument("--type", required=True, action='append', choices=all_restore_types, help="Tipo a restaurar. Use 'custom' para backups personalizados.")
    parser_r.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.operation == "backup":
        if args.backup_type == 'csv':
            try:
                with open(args.servers_csv, mode='r', encoding='utf-8') as s_file:
                    reader = csv.DictReader(s_file)
                    for row in reader:
                        hostname = row['hostname'].strip()
                        roles = [r.strip() for r in row['type'].strip().lower().split(';')]
                        perform_role_backup(hostname, roles, args.mode, args.remote_dir, args.local_dir, args.dry_run)
                        print("-" * 60)
            except Exception as e:
                logging.critical("Erro fatal durante o backup: {}".format(e))
        elif args.backup_type == 'custom':
            perform_custom_backup(args.hostname, args.path, args.remote_dir, args.local_dir, args.dry_run)
            
    elif args.operation == "restore":
        perform_restore(args.hostname, args.type, args.source_file, args.dry_run)
        
    logging.info("Processo concluído.")


if __name__ == "__main__":
    main()
