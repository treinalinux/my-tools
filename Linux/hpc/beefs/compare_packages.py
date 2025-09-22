#!/usr/bin/env python3
#
# name.........: compare_packages
# description..: Compare packages
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 9/22/2025
# github.......: github.com/treinalinux
#
#
#
# /workspace/
# |
# |-- A/
# |   |-- servidorA1.csv
# |   |-- servidorA2.csv
# |
# |-- B/
# |   |-- servidorB1.csv
# |
# |-- C/
# |   |-- servidorC1.csv
# |
# `-- compare_packages.py
# 
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import csv

# --- CONFIGURAÇÃO ---
# Define os nomes dos diretórios para cada grupo de servidores.
DIRETORIOS = {
    'A': 'A',
    'B': 'B',
    'C': 'C'
}
# Define o nome da coluna que contém os pacotes nos arquivos CSV.
COLUNA_PACOTES = 'pacotes'
# --------------------

def ler_pacotes_do_csv(caminho_arquivo: str) -> set:
    """
    Lê um arquivo CSV usando a biblioteca nativa 'csv' e extrai os pacotes.

    Args:
        caminho_arquivo: O caminho completo para o arquivo CSV.

    Returns:
        Um conjunto (set) com a lista de pacotes. Retorna um conjunto vazio
        se o arquivo não puder ser lido ou a coluna não for encontrada.
    """
    pacotes = set()
    try:
        with open(caminho_arquivo, mode='r', encoding='utf-8') as arquivo_csv:
            leitor = csv.reader(arquivo_csv)
            
            # Lê o cabeçalho para encontrar o índice da coluna de pacotes
            try:
                cabecalho = next(leitor)
            except StopIteration:
                return set() # Arquivo vazio

            try:
                # Encontra o índice da coluna pelo nome
                indice_coluna = cabecalho.index(COLUNA_PACOTES)
            except ValueError:
                print(f"AVISO: A coluna '{COLUNA_PACOTES}' não foi encontrada em '{caminho_arquivo}'.")
                return set()

            # Itera sobre as linhas restantes do arquivo
            for linha in leitor:
                try:
                    # Adiciona o pacote ao conjunto, se a linha não for vazia
                    if linha and linha[indice_coluna].strip():
                        pacotes.add(linha[indice_coluna].strip())
                except IndexError:
                    # Ignora linhas malformadas que não têm a coluna esperada
                    continue
    
    except FileNotFoundError:
        print(f"ERRO: Arquivo não encontrado: '{caminho_arquivo}'.")
    except Exception as e:
        print(f"ERRO: Não foi possível ler o arquivo '{caminho_arquivo}'. Detalhes: {e}")
    
    return pacotes


def analisar_grupo_a(diretorio_a: str) -> (str, set):
    """
    Analisa todos os servidores do Grupo A para eleger um servidor de referência.

    A regra é: elege um servidor que possua exatamente o conjunto de pacotes
    comuns a TODOS os servidores do grupo. Se todos forem idênticos,
    o primeiro da lista é escolhido como referência.

    Args:
        diretorio_a: O caminho para o diretório do Grupo A.

    Returns:
        Uma tupla contendo o nome do servidor de referência e o conjunto
        de pacotes dele. Retorna (None, None) se não for possível eleger um.
    """
    print("--- Analisando Grupo A para eleger servidor de referência ---")
    
    try:
        arquivos = [f for f in os.listdir(diretorio_a) if f.endswith('.csv')]
        caminhos_csv = [os.path.join(diretorio_a, f) for f in arquivos]
    except FileNotFoundError:
        print(f"ERRO: O diretório '{diretorio_a}' não foi encontrado.")
        return None, None

    if not caminhos_csv:
        print("ERRO: Nenhum arquivo CSV encontrado no diretório do Grupo A.")
        return None, None

    # Carrega os pacotes de todos os servidores do grupo A em um dicionário
    dados_servidores_a = {os.path.basename(f): ler_pacotes_do_csv(f) for f in caminhos_csv}

    # Pega o primeiro conjunto de pacotes para iniciar a interseção
    lista_de_pacotes = list(dados_servidores_a.values())
    if not lista_de_pacotes:
        return None, None
        
    pacotes_comuns = lista_de_pacotes[0].copy()

    # Calcula a interseção para encontrar os pacotes comuns a todos
    for pacotes_servidor in lista_de_pacotes[1:]:
        pacotes_comuns.intersection_update(pacotes_servidor)

    if not pacotes_comuns:
        print("AVISO: Não há nenhum pacote em comum entre todos os servidores do Grupo A.")
        return None, None

    print(f"Total de pacotes em comum no Grupo A: {len(pacotes_comuns)}")

    # Encontra um servidor que tenha EXATAMENTE a lista de pacotes comuns
    for nome_servidor, pacotes in dados_servidores_a.items():
        if pacotes == pacotes_comuns:
            print(f"Servidor de referência eleito: '{nome_servidor}' (possui exatamente os pacotes comuns).")
            return nome_servidor, pacotes_comuns
    
    # Se ninguém tiver APENAS os pacotes comuns, verifica se todos são iguais
    primeiro_pacote_set = lista_de_pacotes[0]
    todos_iguais = all(p_set == primeiro_pacote_set for p_set in lista_de_pacotes)
    
    if todos_iguais:
        nome_referencia = os.path.basename(caminhos_csv[0])
        print(f"Todos os servidores do Grupo A são idênticos. Servidor de referência eleito: '{nome_referencia}' (o primeiro da lista).")
        return nome_referencia, primeiro_pacote_set

    print("ERRO: Não foi possível eleger um servidor de referência. Nenhum servidor possui apenas os pacotes comuns e nem todos são idênticos.")
    return None, None


def comparar_e_relatar_diferencas(nome_grupo: str, diretorio: str, pacotes_referencia: set):
    """
    Compara os servidores de um grupo com a lista de pacotes de referência.

    Args:
        nome_grupo: O nome do grupo (ex: 'B').
        diretorio: O caminho para o diretório do grupo.
        pacotes_referencia: O conjunto de pacotes do servidor de referência.
    """
    print(f"\n--- Comparando servidores do Grupo {nome_grupo} com a referência ---")
    try:
        arquivos = [f for f in os.listdir(diretorio) if f.endswith('.csv')]
        caminhos_csv = [os.path.join(diretorio, f) for f in arquivos]
    except FileNotFoundError:
        print(f"ERRO: O diretório '{diretorio}' não foi encontrado.")
        return

    if not caminhos_csv:
        print(f"Nenhum arquivo CSV encontrado no diretório do Grupo {nome_grupo}.")
        return

    for caminho_csv in caminhos_csv:
        nome_servidor = os.path.basename(caminho_csv)
        pacotes_servidor_atual = ler_pacotes_do_csv(caminho_csv)

        # Calcula a diferença: pacotes que estão na referência mas não no servidor atual
        pacotes_faltantes = pacotes_referencia - pacotes_servidor_atual

        if not pacotes_faltantes:
            print(f"✅ Servidor '{nome_servidor}' está em conformidade. Nenhum pacote faltando.")
        else:
            print(f"❌ Servidor '{nome_servidor}' - Pacotes faltando ({len(pacotes_faltantes)}):")
            for pacote in sorted(list(pacotes_faltantes)):
                print(f"  - {pacote}")


def main():
    """
    Função principal que orquestra a execução do script.
    """
    # 1. Eleger o servidor de referência do Grupo A
    servidor_referencia, pacotes_referencia = analisar_grupo_a(DIRETORIOS['A'])

    if not servidor_referencia:
        print("\nProcesso interrompido devido à falha na eleição do servidor de referência.")
        return

    # 2. Comparar a referência com os servidores dos grupos B e C
    for grupo, diretorio in DIRETORIOS.items():
        if grupo != 'A':
            comparar_e_relatar_diferencas(grupo, diretorio, pacotes_referencia)


if __name__ == "__main__":
    main()
