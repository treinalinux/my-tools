import shutil
import os
import csv

#
# Alan Alves
# 
# Ferramentas para trabalhar com espaço em disco
# 


def format_bytes(size_in_bytes):
    """
    Converte um tamanho em bytes para um formato legível por humanos (KB, MB, GB, TB, PB).
    """
    if size_in_bytes is None:
        return "N/A"
    
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T', 5: 'P'}
    
    while size_in_bytes >= power and n < len(power_labels) - 1:
        size_in_bytes /= power
        n += 1
        
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_disk_space(path):
    """
    Retorna o espaço total, usado e livre do disco para um determinado caminho.

    Args:
        path (str): O caminho do sistema de arquivos a ser verificado.

    Returns:
        tuple: Uma tupla contendo o espaço total, usado e livre em bytes.
               Retorna (None, None, None) se o caminho não existir.
    """
    try:
        # Resolve o caminho para obter o ponto de montagem real
        real_path = os.path.realpath(path)
        if not os.path.exists(real_path):
            print(f"Aviso: O caminho '{path}' não existe.")
            return (None, None, None)
    except OSError as e:
        print(f"Aviso: Não foi possível verificar o caminho '{path}': {e}")
        return (None, None, None)

    total, used, free = shutil.disk_usage(real_path)
    return (total, used, free)

# --- Nova Função Reutilizável para Exportar CSV com Filtros ---

def export_disk_space_to_csv(paths_to_check, output_filename, filters=None):
    """
    Verifica o espaço em disco para uma lista de caminhos, aplica filtros
    e exporta o resultado para um arquivo CSV.

    Args:
        paths_to_check (list): Uma lista de strings com os caminhos a serem verificados.
        output_filename (str): O nome do arquivo CSV a ser gerado (ex: 'relatorio_disco.csv').
        filters (list, optional): Uma lista de dicionários, onde cada dicionário é um filtro.
                                  Ex: [{'type': 'percentage_used', 'condition': 'gt', 'value': 80}]
                                  Tipos suportados: 'percentage_used', 'free_space_gb'.
                                  Condições suportadas: 'gt' (maior que), 'lt' (menor que).
                                  Defaults to None (sem filtros).
    """
    if filters is None:
        filters = []
        
    processed_data = []
    
    # Coleta e processa os dados de cada caminho
    for path in paths_to_check:
        total, used, free = get_disk_space(path)
        
        if total is None:
            continue
            
        # Calcula métricas para filtragem e relatório
        percentage_used = (used / total) * 100 if total > 0 else 0
        free_space_gb = free / (1024**3)
        
        # Armazena os dados em um dicionário
        disk_info = {
            'path': path,
            'total_formatado': format_bytes(total),
            'usado_formatado': format_bytes(used),
            'livre_formatado': format_bytes(free),
            'percentual_usado': round(percentage_used, 2),
            'espaco_livre_gb': round(free_space_gb, 2)
        }
        
        # Lógica de Filtragem
        keep_data = True # Assume que os dados devem ser mantidos, a menos que um filtro falhe
        for rule in filters:
            filter_type = rule.get('type')
            condition = rule.get('condition')
            value = rule.get('value')

            if filter_type == 'percentage_used':
                metric_to_check = percentage_used
            elif filter_type == 'free_space_gb':
                metric_to_check = free_space_gb
            else:
                continue # Pula regras de filtro desconhecidas

            # Aplica a condição
            if condition == 'gt' and not metric_to_check > value:
                keep_data = False
                break
            if condition == 'lt' and not metric_to_check < value:
                keep_data = False
                break
        
        if keep_data:
            processed_data.append(disk_info)

    # Escreve os dados filtrados no arquivo CSV
    if not processed_data:
        print("Nenhum dado para exportar após aplicar os filtros.")
        return

    try:
        # Define os cabeçalhos das colunas no CSV
        fieldnames = ['path', 'total_formatado', 'usado_formatado', 'livre_formatado', 'percentual_usado', 'espaco_livre_gb']
        
        with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(processed_data)
            
        print(f"Dados exportados com sucesso para o arquivo '{output_filename}'")
        
    except IOError as e:
        print(f"Erro ao escrever no arquivo CSV: {e}")


# --- Exemplo de Uso ---
if __name__ == "__main__":
    
    # Lista de pontos de montagem e diretórios comuns no Linux para verificar
    common_paths = [
        '/',
        '/home',
        '/var',
        '/tmp',
        '/boot',
        '/caminho/que/nao/existe' # Para testar o tratamento de erro
    ]
    
    print("--- Exemplo 1: Exportando todos os dados sem filtros ---")
    export_disk_space_to_csv(common_paths, 'relatorio_disco_completo.csv')
    
    print("\n" + "="*50 + "\n")
    
    # ---
    
    print("--- Exemplo 2: Exportando apenas partições com mais de 10% de uso ---")
    # Define o filtro: percentual de uso deve ser 'maior que' (gt) 10
    filters_high_usage = [
        {'type': 'percentage_used', 'condition': 'gt', 'value': 10}
    ]
    export_disk_space_to_csv(common_paths, 'relatorio_alta_utilizacao.csv', filters=filters_high_usage)

    print("\n" + "="*50 + "\n")

    # ---

    print("--- Exemplo 3: Exportando apenas partições com menos de 50 GB de espaço livre ---")
    # Define o filtro: espaço livre em GB deve ser 'menor que' (lt) 50
    filters_low_space = [
        {'type': 'free_space_gb', 'condition': 'lt', 'value': 50}
    ]
    export_disk_space_to_csv(common_paths, 'relatorio_pouco_espaco.csv', filters=filters_low_space)
