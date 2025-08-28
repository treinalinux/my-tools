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
palavra-chave e gera um relatório em HTML otimizado para clientes de e-mail como o Outlook.
"""

import psutil
import sys
from datetime import datetime
import pytz

# ... (as funções format_bytes e get_disk_stats_by_keyword continuam as mesmas) ...

def format_bytes(byte_size):
    if byte_size == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    import math
    i = int(math.floor(math.log(byte_size, 1024)))
    p = math.pow(1024, i)
    s = round(byte_size / p, 2)
    return f"{s} {size_name[i]}"

def get_disk_stats_by_keyword(keyword):
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

def gerar_saida_html_para_outlook(keyword, total, used, free, percent_used):
    """
    Gera um arquivo HTML robusto e compatível com clientes de e-mail, incluindo o Microsoft Outlook.
    Utiliza tabelas para layout e CSS inline.
    """
    # Formatação dos valores
    total_str = format_bytes(total)
    used_str = format_bytes(used)
    free_str = format_bytes(free)
    percent_str = f"{percent_used:.2f}%"

    # Define a cor sólida da barra com base no uso
    if percent_used < 75:
        progress_color = "#28a745"  # Verde
    elif percent_used < 90:
        progress_color = "#ffc107"  # Amarelo
    else:
        progress_color = "#dc3545"  # Vermelho
        
    # Obtém a data e hora atuais
    try:
        fuso_horario = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso_horario)
        timestamp = agora.strftime("%d/%m/%Y às %H:%M:%S (%Z)")
    except Exception:
        timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    # Ícones SVG (bem suportados em clientes modernos, mas podem não aparecer em Outlooks muito antigos)
    # Uma alternativa mais segura seria usar imagens hospedadas externamente.
    icon_total = '📊' # Usando emojis como fallback super compatível
    icon_used = '📈'
    icon_free = '📋'

    # Template HTML para E-mail
    html_template = f"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Relatório de Disco - {keyword}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: Arial, Helvetica, sans-serif;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse;">
        <tr>
            <td align="center" style="padding: 20px 0 30px 0;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; border: 1px solid #cccccc; border-radius: 8px;">
                    <tr>
                        <td align="center" style="padding: 30px 20px 20px 20px; border-bottom: 1px solid #eeeeee;">
                            <h1 style="color: #2c3e50; margin: 0; font-size: 24px;">Relatório de Uso de Disco</h1>
                            <p style="color: #7f8c8d; margin: 5px 0 0 0; font-size: 16px;">
                                Análise para a palavra-chave: 
                                <span style="color: #3498db; font-weight: bold;">"{keyword}"</span>
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 30px 25px 30px 25px;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse;">
                                <tr>
                                    <td style="font-size: 18px; color: #2c3e50; padding-bottom: 20px;" colspan="2">
                                        <b>Resumo Geral</b>
                                    </td>
                                </tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2;">
                                        <span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_total}</span>
                                        <span style="color: #555555; font-size: 16px; vertical-align: middle;">Espaço Total</span>
                                    </td>
                                    <td width="50%" align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold; color: #2c3e50;">
                                        {total_str}
                                    </td>
                                </tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2;">
                                        <span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_used}</span>
                                        <span style="color: #555555; font-size: 16px; vertical-align: middle;">Espaço em Uso</span>
                                    </td>
                                    <td width="50%" align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold; color: #2c3e50;">
                                        {used_str}
                                    </td>
                                </tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0;">
                                        <span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_free}</span>
                                        <span style="color: #555555; font-size: 16px; vertical-align: middle;">Disponível</span>
                                    </td>
                                    <td width="50%" align="right" style="padding: 12px 0; font-size: 18px; font-weight: bold; color: #2c3e50;">
                                        {free_str}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 25px 30px 25px;">
                            <p style="text-align: center; margin-top: 0; color: #2c3e50; font-size: 16px; font-weight: bold;">Ocupação Geral: {percent_str}</p>
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-radius: 5px; background-color: #e9ecef;">
                                <tr>
                                    <td width="{percent_str}" bgcolor="{progress_color}" style="border-radius: 5px; text-align: center; color: #ffffff; font-size: 14px; line-height: 20px;">
                                        &nbsp;
                                    </td>
                                    <td></td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                     <tr>
                        <td bgcolor="#ecf0f1" style="padding: 20px 30px; text-align: center; color: #888888; font-size: 12px;">
                            Relatório gerado em: {timestamp}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    try:
        filename = "relatorio_para_outlook.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html_template)
        print(f"\n\033[92m✔ Relatório compatível com Outlook '{filename}' gerado com sucesso!\033[0m")
    except Exception as e:
        print(f"\n\033[91mErro ao gerar o arquivo HTML: {e}\033[0m")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Uso: python3 {sys.argv[0]} <palavra-chave>")
        sys.exit(1)

    search_keyword = sys.argv[1]
    total, used, free = get_disk_stats_by_keyword(search_keyword)

    if total > 0:
        percent_used = (used / total) * 100

        # Saída no Terminal
        print(f"--- Estatísticas de Disco para a chave '{search_keyword}' ---")
        print(f"Total.....: {format_bytes(total)}")
        print(f"Em Uso....: {format_bytes(used)}")
        print(f"Disponível: {format_bytes(free)}")
        print(f"Ocupação..: {percent_used:.2f}%")
        
        # Geração do Arquivo HTML para Outlook
        gerar_saida_html_para_outlook(search_keyword, total, used, free, percent_used)
