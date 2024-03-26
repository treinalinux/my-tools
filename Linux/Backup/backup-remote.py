#!/usr/bin/python3
# 
# Alan S. Alves
# 03/24/2024
# Tools Remote Backup
# 
# ##########################################################
# ##########################################################

import subprocess

# ##########################################################
#  Vars
# ##########################################################

add_folders_bkp = [
        "Documentos", "Imagens", "Faculdade", "Projetos",
        "Downloads", "Python"]
src_dir = "/home/alan"
dst_dir = "/home/alan/notebook/backup"
target = "192.168.0.228"
port_dst = "ssh -p 2800"


# ##########################################################
# Functions
# ##########################################################


def backup_rsync(src, dst, user, host, port="ssh -p 22"):
    conexao = (f"{user}@{host}:{dst}")
    cmd_start = (f"""
        rsync -ar --progress {src} -e
            """)
    comando = cmd_start.split()
    comando.append(port)
    comando.append(conexao)
    subprocess.run(comando)


# ##########################################################
# Main exection
# ##########################################################

for pasta in add_folders_bkp:
    backup_folder = (f"{src_dir}/{pasta}")
    print(f"\nFazendo backup de: {backup_folder}")
    backup_rsync(backup_folder, dst_dir, "alan", target, port_dst)
