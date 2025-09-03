#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: compare_list
# description..: Compare files csv and generate new file
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 8/3/2024

#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import csv
import argparse

def processar_arquivos_csv(base_path, completo_path):
    """
    Processa dois arquivos CSV para encontrar e separar dados de ativos.

    Args:
        base_path (str): Caminho para o arquivo CSV base com os números de série.
        completo_path (str): Caminho para o arquivo CSV completo com todas as informações.
    """
    print(f"Iniciando o processamento dos arquivos...")
    
    # Lista de colunas esperada no arquivo completo
    colunas_completas = ['numero_de_serie', 'modelo_equipamento', 'nome_do_host', 'ip', 'tipo_de_so']
    
    # Conjunto para armazenar os números de série do arquivo base para uma busca eficiente
    numeros_de_serie_base = set()
    try:
        with open(base_path, 'r', newline='', encoding='utf-8') as f_base:
            reader_base = csv.reader(f_base)
            # Ignora o cabeçalho
            next(reader_base)
            for row in reader_base:
                if row:
                    numeros_de_serie_base.add(row[0].strip()) # Adiciona o numero de série
        print(f"Total de {len(numeros_de_serie_base)} números de série lidos do arquivo base.")
    except FileNotFoundError:
        print(f"Erro: O arquivo base '{base_path}' não foi encontrado.")
        return
    except Exception as e:
        print(f"Ocorreu um erro ao ler o arquivo base: {e}")
        return

    # Conjunto para armazenar os números de série que foram encontrados
    numeros_de_serie_encontrados = set()
    
    # Lista para armazenar as linhas completas dos ativos encontrados
    linhas_encontradas = []

    try:
        with open(completo_path, 'r', newline='', encoding='utf-8') as f_completo:
            reader_completo = csv.reader(f_completo)
            # Ignora o cabeçalho
            next(reader_completo)
            for row in reader_completo:
                if row and row[0].strip() in numeros_de_serie_base:
                    linhas_encontradas.append(row)
                    numeros_de_serie_encontrados.add(row[0].strip())
        print(f"Total de {len(numeros_de_serie_encontrados)} números de série encontrados no arquivo completo.")
    except FileNotFoundError:
        print(f"Erro: O arquivo completo '{completo_path}' não foi encontrado.")
        return
    except Exception as e:
        print(f"Ocorreu um erro ao ler o arquivo completo: {e}")
        return

    # Escreve o arquivo de ativos encontrados
    try:
        nome_encontrados = 'ativos_encontrados.csv'
        with open(nome_encontrados, 'w', newline='', encoding='utf-8') as f_encontrados:
            writer_encontrados = csv.writer(f_encontrados)
            writer_encontrados.writerow(colunas_completas)
            for linha in linhas_encontradas:
                writer_encontrados.writerow(linha)
        print(f"Arquivo '{nome_encontrados}' gerado com sucesso!")
    except Exception as e:
        print(f"Ocorreu um erro ao escrever o arquivo '{nome_encontrados}': {e}")
    
    # Escreve o arquivo de ativos faltando
    try:
        numeros_de_serie_faltando = numeros_de_serie_base.difference(numeros_de_serie_encontrados)
        nome_faltando = 'ativos_faltando.csv'
        with open(nome_faltando, 'w', newline='', encoding='utf-8') as f_faltando:
            writer_faltando = csv.writer(f_faltando)
            writer_faltando.writerow(['numero_de_serie_faltando'])
            for numero in sorted(list(numeros_de_serie_faltando)):
                writer_faltando.writerow([numero])
        print(f"Arquivo '{nome_faltando}' gerado com sucesso!")
        print(f"Total de {len(numeros_de_serie_faltando)} números de série faltando.")
    except Exception as e:
        print(f"Ocorreu um erro ao escrever o arquivo '{nome_faltando}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Processa arquivos CSV de ativos para encontrar e separar dados.')
    parser.add_argument('base_file', type=str, help='Caminho para o arquivo CSV base (número de série, modelo).')
    parser.add_argument('full_file', type=str, help='Caminho para o arquivo CSV completo (todos os dados).')
    
    args = parser.parse_args()
    processar_arquivos_csv(args.base_file, args.full_file)
