#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: calc_space_total
# description..: Calc space total of disks mounted used same keyword
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 8/27/2024
# github.......: github.com/treinalinux/
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


"""
Verifica o espaço em disco de pontos de montagem filtrados por uma
palavra-chave passada como argumento.

Calcula o espaço total, em uso, disponível e a porcentagem de uso.
"""

import psutil
import sys

def format_bytes(byte_size):
    """
    Formata o tamanho em bytes para uma representação legível (KB, MB, GB, etc.).
    """
    if byte_size == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    import math
    i = int(math.floor(math.log(byte_size, 1024)))
    p = math.pow(1024, i)
    s = round(byte_size / p, 2)
    return f"{s} {size_name[i]}"

def get_disk_stats_by_keyword(keyword):
    """
    Calcula o espaço total, em uso e disponível para todos os pontos de montagem
    que contêm a palavra-chave fornecida.

    Args:
        keyword (str): A palavra-chave para filtrar os pontos de montagem.

    Retorna:
        tuple: Uma tupla contendo o espaço total, em uso e disponível em bytes.
    """
    total_space = 0
    total_used = 0
    total_free = 0
    
    matching_mounts = []

    try:
        partitions = psutil.disk_partitions()
        for partition in partitions:
            if keyword in partition.mountpoint:
                matching_mounts.append(partition.mountpoint)
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total_space += usage.total
                    total_used += usage.used
                    total_free += usage.free
                except PermissionError:
                    print(f"Aviso: Permissão negada para acessar {partition.mountpoint}. Ignorando.")
                except Exception as e:
                    print(f"Erro ao obter informações de uso para {partition.mountpoint}: {e}")
    except Exception as e:
        print(f"Erro ao listar as partições de disco: {e}")

    if not matching_mounts:
        print(f"Nenhum ponto de montagem encontrado com a palavra-chave: '{keyword}'")

    return total_space, total_used, total_free

if __name__ == "__main__":
    # Verifica se a palavra-chave foi passada como argumento
    if len(sys.argv) < 2:
        print(f"Uso: python3 {sys.argv[0]} <palavra-chave>")
        print("Exemplo: python3 verifica_disco.py beegfs")
        sys.exit(1)

    # Pega a palavra-chave do primeiro argumento da linha de comando
    search_keyword = sys.argv[1]

    total, used, free = get_disk_stats_by_keyword(search_keyword)

    if total > 0:
        # Calcula a porcentagem de uso
        percent_used = (used / total) * 100

        print(f"--- Estatísticas de Disco para pontos de montagem com a chave '{search_keyword}' ---")
        print(f"Espaço Total.....: {format_bytes(total)}")
        print(f"Espaço em Uso....: {format_bytes(used)}")
        print(f"Espaço Disponível: {format_bytes(free)}")
        print(f"Porcentagem de Uso: {percent_used:.2f}%")
    else:
        # Não exibe nada se nenhum disco correspondente foi encontrado e já avisado
        pass
