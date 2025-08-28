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
ESTA VERSÃO NÃO REQUER BIBLIOTECAS EXTERNAS e usa 'os.popen' para compatibilidade.
"""

import sys
from datetime import datetime
import os

# A biblioteca 'pytz' é opcional. Se não estiver instalada, o script usará o horário do
# sistema sem informações de fuso horário.
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
    Calcula o espaço total, em uso e disponível para todos os pontos de montagem
    que contêm a palavra-chave, usando 'os.popen' para executar o comando 'df'.
    """
    total_space = 0
    total_used = 0
    total_free = 0
    
    matching_mounts_found = False
    command = 'df -P'

    try:
        # os.popen executa o comando e retorna um objeto tipo arquivo
        with os.popen(command) as pipe:
            output = pipe.read()
        
        output_lines = output.strip().split('\n')
        
        # Ignora a primeira linha (cabeçalho)
        for line in output_lines[1:]:
            parts = line.split()
            
            if len(parts) >= 6:
                mount_point = parts[5]
                
                if keyword in mount_point:
                    matching_mounts_found = True
                    try:
                        # Multiplica por 1024 para converter de blocos de 1K para bytes
                        total_space += int(parts[1]) * 1024
                        total_used += int(parts[2]) * 1024
                        total_free += int(parts[3]) * 1024
                    except ValueError:
                        print(f"Aviso: Não foi possível processar a linha para o ponto de montagem {mount_point}. Ignorando.")
                        continue

    except Exception as e:
        print(f"Ocorreu um erro ao executar ou processar o comando '{command}': {e}")
        return 0, 0, 0

    if not matching_mounts_found:
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
        progress_color = "#28a745"
    elif percent_used < 90:
        progress_color = "#ffc107"
    else:
        progress_color = "#dc3545"
        
    # Obtém a data e hora atuais. Usa pytz se estiver disponível.
    timestamp = ""
    if pytz:
        try:
            fuso_horario = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(fuso_horario)
            timestamp = agora.strftime("%d/%m/%Y às %H:%M:%S (%Z)")
        except Exception:
            timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    else:
        timestamp = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    icon_total = '📊'
    icon_used = '📈'
    icon_free = '📋'

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
                                <tr><td style="font-size: 18px; color: #2c3e50; padding-bottom: 20px;" colspan="2"><b>Resumo Geral</b></td></tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2;"><span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_total}</span><span style="color: #555555; font-size: 16px; vertical-align: middle;">Espaço Total</span></td>
                                    <td width="50%" align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold; color: #2c3e50;">{total_str}</td>
                                </tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2;"><span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_used}</span><span style="color: #555555; font-size: 16px; vertical-align: middle;">Espaço em Uso</span></td>
                                    <td width="50%" align="right" style="padding: 12px 0; border-bottom: 1px solid #f2f2f2; font-size: 18px; font-weight: bold; color: #2c3e50;">{used_str}</td>
                                </tr>
                                <tr>
                                    <td width="50%" style="padding: 12px 0;"><span style="font-size: 20px; vertical-align: middle; padding-right: 10px;">{icon_free}</span><span style="color: #555555; font-size: 16px; vertical-align: middle;">Disponível</span></td>
                                    <td width="50%" align="right" style="padding: 12px 0; font-size: 18px; font-weight: bold; color: #2c3e50;">{free_str}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 25px 30px 25px;">
                            <p style="text-align: center; margin-top: 0; color: #2c3e50; font-size: 16px; font-weight: bold;">Ocupação Geral: {percent_str}</p>
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-radius: 5px; background-color: #e9ecef;">
                                <tr>
                                    <td width="{percent_str}" bgcolor="{progress_color}" style="border-radius: 5px; text-align: center; color: #ffffff; font-size: 14px; line-height: 20px;">&nbsp;</td>
                                    <td></td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                     <tr>
                        <td bgcolor="#ecf0f1" style="padding: 20px 30px; text-align: center; color: #888888; font-size: 12px;">Relatório gerado em: {timestamp}</td>
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

        print(f"--- Estatísticas de Disco para a chave '{search_keyword}' ---")
        print(f"Total.....: {format_bytes(total)}")
        print(f"Em Uso....: {format_bytes(used)}")
        print(f"Disponível: {format_bytes(free)}")
        print(f"Ocupação..: {percent_used:.2f}%")
        
        gerar_saida_html_para_outlook(search_keyword, total, used, free, percent_used)
