#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name.........: Backup BeeGFS & HA Smart Backup Tool
# description..: Ferramenta de Backup BeeGFS
# author.......: Alan da Silva Alves
# version......: 0.0.1
# date.........: 5/26/2026
# depends......: ethtool
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import sys
import json
import socket
import argparse
import tarfile
import hashlib
from datetime import datetime

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

CONFIG_PATH = "/opt/beegfs_backup/backup_config.json"
STATE_PATH = "/opt/beegfs_backup/.backup_state.json"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def run_cmd(cmd):
    """Executa comandos via shell com proteção."""
    try:
        safe_cmd = cmd if "2>" in cmd else f"{cmd} 2>/dev/null"
        with os.popen(safe_cmd) as proc:
            return proc.read().strip()
    except Exception:
        return ""


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERRO] Configuração {CONFIG_PATH} inexistente.")
        sys.exit(1)
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)


def get_file_hash(filepath):
    """Gera a assinatura SHA-256 de um arquivo."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def get_path_hash(path):
    """Gera assinatura de um arquivo isolado ou um diretório inteiro."""
    if os.path.isfile(path):
        return get_file_hash(path)
    elif os.path.isdir(path):
        hasher = hashlib.sha256()
        # Varrer o diretório e ordenar garante que a assinatura seja sempre consistente
        for root, dirs, files in os.walk(path):
            for name in sorted(files):
                filepath = os.path.join(root, name)
                h = get_file_hash(filepath)
                if h:
                    hasher.update(h.encode('utf-8'))
        return hasher.hexdigest()
    return ""


def check_for_changes(tier, paths):
    """Compara as assinaturas atuais com as do último backup."""
    current_state = {}
    has_changes = False
    
    old_state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r') as f:
                old_state = json.load(f)
        except Exception:
            pass
            
    old_tier_state = old_state.get(tier, {})

    for p in paths:
        if os.path.exists(p):
            current_state[p] = get_path_hash(p)
        else:
            current_state[p] = "NOT_FOUND"
            
    if current_state != old_tier_state:
        has_changes = True
        
    return has_changes, current_state, old_state


def save_state(full_state):
    """Salva as novas assinaturas após um backup bem sucedido."""
    try:
        with open(STATE_PATH, 'w') as f:
            json.dump(full_state, f, indent=4)
    except Exception as e:
        print(f"[AVISO] Erro ao gravar arquivo de estado: {e}")


def backup_pacemaker(dest_dir, hostname):
    if run_cmd("systemctl is-active pacemaker") == "active":
        print("  [*] Pacemaker ativo detectado. Extraindo XML do cluster...")
        cib_file = os.path.join(dest_dir, f"pacemaker_cib_{hostname}.xml")
        run_cmd(f"pcs cluster cib > {cib_file}")
        return cib_file
    return None


def perform_backup(tier, config):
    if tier not in config['tiers']:
        print(f"[ERRO] Tier '{tier}' não mapeado no config.")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n[{timestamp}] Avaliando backup do tier: {tier.upper()}")
    print("-" * 60)

    paths_to_backup = config['tiers'][tier]
    
    # 1. Inteligência: Avalia se os arquivos mudaram antes de fazer qualquer coisa
    has_changes, current_tier_state, full_state = check_for_changes(tier, paths_to_backup)
    
    if not has_changes:
        print(f"  [SKIPPED] Nenhuma alteração detectada. Backup ignorado para economizar disco.\n")
        return

    dest_dir = config.get("backup_destination", "/tmp/beegfs_backups")
    os.makedirs(dest_dir, exist_ok=True)
    hostname = socket.getfqdn()
    tar_filename = os.path.join(dest_dir, f"backup_{tier}_{hostname}_{timestamp}.tar.gz")
    files_added = 0

    # 2. Executa backup lógico (Pacemaker)
    cib_path = backup_pacemaker(dest_dir, hostname)
    if cib_path:
        paths_to_backup_run = paths_to_backup + [cib_path]
    else:
        paths_to_backup_run = paths_to_backup.copy()

    # 3. Empacotamento Físico
    try:
        with tarfile.open(tar_filename, "w:gz") as tar:
            for path in paths_to_backup_run:
                if os.path.exists(path):
                    tar.add(path, arcname=os.path.abspath(path).lstrip('/'))
                    print(f"  [+] Copiado: {path}")
                    files_added += 1
                else:
                    print(f"  [!] Ignorado (não encontrado): {path}")
        
        if cib_path and os.path.exists(cib_path):
            os.remove(cib_path)

        if files_added > 0:
            print("-" * 60)
            print(f"[OK] Novo backup gerado: {tar_filename} ({os.path.getsize(tar_filename) / 1024:.1f} KB)\n")
            
            # 4. Atualiza o cofre de assinaturas apenas após o sucesso
            full_state[tier] = current_tier_state
            save_state(full_state)
        else:
            print(f"\n[AVISO] Arquivo {tar_filename} vazio. Estado não atualizado.\n")

    except PermissionError:
        print("\n[ERRO] Permissão negada. Você está rodando como root?")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="BeeGFS & HA Smart Backup Tool")
    parser.add_argument("tier", choices=["management", "metadata", "storage", "all"], help="Qual perfil do nó realizar backup")
    args = parser.parseargs() if hasattr(parser, 'parseargs') else parser.parse_args()

    config = load_config()

    if args.tier == "all":
        for t in config['tiers'].keys():
            perform_backup(t, config)
    else:
        perform_backup(args.tier, config)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
