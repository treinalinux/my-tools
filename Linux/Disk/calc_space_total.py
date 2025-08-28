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
palavra-chave, gera um relatório em HTML (compatível com Outlook)
incluindo o detalhamento da volumetria de cada ponto de montagem verificado.
Usa 'os.popen' e não requer bibliotecas externas.
"""

import sys
from datetime import datetime
import os

# A biblioteca 'pytz' é opcional.
try:
    import pytz
except ImportError:
    pytz = None

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
    Calcula os totais e também coleta as estatísticas individuais de cada
    ponto de montagem que contém a palavra-chave.
    """
    total_space = 0
    total_used = 0
    total_free = 0
    detailed_stats = []
    
    command = 'df -P'

    try:
        with os.popen(command) as pipe:
            output = pipe.read()
        
        output_lines = output.strip().split('\n')
        
        for line in output_lines[1:]:
            parts = line.split()
            
            if len(parts) >= 6:
                mount_point = parts[5]
                
                if keyword in mount_point:
                    try:
                        # Dados individuais
                        mount_total = int(parts[1]) * 1024
                        mount_used = int(parts[2]) * 1024
                        mount_free = int(parts[3]) * 1024
                        
                        # Acumula os totais gerais
                        total_space += mount_total
                        total_used += mount_used
                        total_free += mount_free
                        
                        # Calcula a porcentagem individual
                        percent = (mount_used / mount_total) * 100 if mount_total > 0 else 0
                        
                        # Adiciona à lista de detalhes
                        detailed_stats.append({
                            "mount": mount_point,
                            "total": mount_total,
                            "used": mount_used,
                            "percent": percent
                        })
                    except ValueError:
                        print(f"Aviso: Não foi possível processar a linha para o ponto de montagem {mount_point}. Ignorando.")
                        continue

    except Exception as e:
        print(f"Ocorreu um erro ao executar ou processar o comando '{command}': {e}")
        return 0, 0, 0, []

    if not detailed_stats:
        print(f"Nenhum ponto de montagem encontrado com a palavra-chave: '{keyword}'")

    # Ordena a lista de detalhes pelo nome do ponto de montagem
    detailed_stats.sort(key=lambda x: x['mount'])
    
    return total_space, total_used, total_free, detailed_stats

def gerar_saida_html_para_outlook(keyword, total, used, free, percent_used, mount_details):
    """
    Gera um arquivo HTML compatível com Outlook, agora com uma tabela
    detalhando a volumetria de cada ponto de montagem.
    """
    total_str = format_bytes(total)
    used_str = format_bytes(used)
    free_str = format_bytes(free)
    percent_str = f"{percent_used:.2f}%"

    if percent_used < 75:
        progress_color_total = "#28a745"
    elif percent_used < 90:
        progress_color_total = "#ffc107"
    else:
        progress_color_total = "#dc3545"
        
    timestamp = ""
    if pytz:
        try:
            fuso_horario = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(fuso_horario)
            timestamp = agora.strftime("%d/%m/%Y às %H:%M:%S (%Z)")
        except Exception:
            timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    else:
        timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M:%S (%Z)")

    # Geração da tabela de detalhes
    details_rows_html = ""
    for item in mount_details:
        item_percent_str = f"{item['percent']:.2f}%"
        
        if item['percent'] < 75:
            progress_color_item = "#28a745"
        elif item['percent'] < 90:
            progress_color_item = "#ffc107"
        else:
            progress_color_item = "#dc3545"

        details_rows_html += f"""
        <tr>
            <td style="padding: 10px 5px; border-bottom: 1px solid #eeeeee; font-family: 'Courier New', Courier, monospace; font-size: 14px; color: #333;">
                {item['mount']}
            </td>
            <td style="padding: 10px 5px; border-bottom: 1px solid #eeeeee; font-size: 14px; color: #333; text-align: right;">
                {format_bytes(item['used'])} / {format_bytes(item['total'])}
            </td>
            <td style="padding: 10px 5px; border-bottom: 1px solid #eeeeee; font-size: 14px; color: #333; text-align: right; width: 120px;">
                <table border="0" cellpadding="0" cellspacing="0" width="100%"><tr>
                <td width="55" align="right" style="padding-right: 5px;">{item_percent_str}</td>
                <td style="background-color: #e9ecef; border-radius: 3px; width: 65px;">
                    <table border="0" cellpadding="0" cellspacing="0" width="{item['percent']}%">
                        <tr><td bgcolor="{progress_color_item}" height="10" style="border-radius: 3px;"></td></tr>
                    </table>
                </td>
                </tr></table>
            </td>
        </tr>
        """

    html_template = f"""
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: Arial, Helvetica, sans-serif;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse;">
        <tr><td align="center" style="padding: 20px 0 30px 0;">
            <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; border: 1px solid #cccccc; border-radius: 8px;">
                <tr><td align="center" style="padding: 30px 20px 20px 20px; border-bottom: 1px solid #eeeeee;">
                    <h1 style="color: #2c3e50; margin: 0; font-size: 24px;">Relatório de Uso de Disco</h1>
                    <p style="color: #7f8c8d; margin: 5px 0 0 0; font-size: 16px;">
                        Análise para a palavra-chave: <span style="color: #3498db; font-weight: bold;">"{keyword}"</span>
                    </p>
                </td></tr>
                <tr><td style="padding: 30px 25px 10px 25px;">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%">
                        <tr><td style="font-size: 18px; color: #2c3e50; padding-bottom: 20px;" colspan="2"><b>Resumo Geral</b></td></tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 16px;">📊 Espaço Total</td>
                            <td align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold;">{total_str}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 16px;">📈 Espaço em Uso</td>
                            <td align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold;">{used_str}</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px 0; font-size: 16px;">📋 Disponível</td>
                            <td align="right" style="padding: 12px 0; font-size: 18px; font-weight: bold;">{free_str}</td>
                        </tr>
                    </table>
                </td></tr>
                <tr><td style="padding: 20px 25px 30px 25px;">
                    <p style="text-align: center; margin-top: 0; font-size: 16px; font-weight: bold;">Ocupação Geral: {percent_str}</p>
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #e9ecef;">
                        <tr><td width="{percent_str}" bgcolor="{progress_color_total}">&nbsp;</td><td></td></tr>
                    </table>
                </td></tr>
                <tr><td style="padding: 0 25px 30px 25px; border-top: 1px solid #eeeeee;">
                     <p style="font-size: 18px; color: #2c3e50; margin-top: 25px; margin-bottom: 15px;"><b>Detalhamento por Ponto de Montagem</b></p>
                     <table border="0" cellpadding="0" cellspacing="0" width="100%">
                        <thead><tr>
                            <th style="text-align: left; padding: 0 5px 10px 5px; color: #7f8c8d; font-size: 12px; text-transform: uppercase;">Ponto de Montagem</th>
                            <th style="text-align: right; padding: 0 5px 10px 5px; color: #7f8c8d; font-size: 12px; text-transform: uppercase;">Usado / Total</th>
                            <th style="text-align: right; padding: 0 5px 10px 5px; color: #7f8c8d; font-size: 12px; text-transform: uppercase;">Ocupação</th>
                        </tr></thead>
                        <tbody>{details_rows_html}</tbody>
                     </table>
                </td></tr>
                <tr><td bgcolor="#ecf0f1" style="padding: 20px 30px; text-align: center; color: #888888; font-size: 12px;">Relatório gerado em: {timestamp}</td></tr>
            </table>
        </td></tr>
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
    total, used, free, details = get_disk_stats_by_keyword(search_keyword)

    if total > 0:
        percent_used = (used / total) * 100

        print(f"--- Estatísticas de Disco para a chave '{search_keyword}' ---")
        print(f"Total.....: {format_bytes(total)}")
        print(f"Em Uso....: {format_bytes(used)}")
        print(f"Disponível: {format_bytes(free)}")
        print(f"Ocupação..: {percent_used:.2f}%")
        
        print("\n--- Detalhamento por Ponto de Montagem ---")
        if details:
            for item in details:
                print(f"- {item['mount']:<30} | {format_bytes(item['used']):>10} / {format_bytes(item['total']):<10} ({item['percent']:>6.2f}%)")
        else:
            print("Nenhum.")
        
        gerar_saida_html_para_outlook(search_keyword, total, used, free, percent_used, details)
