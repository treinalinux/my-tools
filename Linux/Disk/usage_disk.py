import shutil
import os

#
# Alan Alves
# 
# Ferramentas para trabalhar com espaço em disco
# 

# --- Função Base (necessária para os cálculos) ---

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


# --- Nova Função Reutilizável para Calcular Porcentagens ---

def get_disk_usage_percentages(path):
    """
    Calcula e retorna a porcentagem de espaço em disco usado e disponível.

    Args:
        path (str): O caminho do sistema de arquivos a ser verificado.

    Returns:
        tuple: Uma tupla contendo (percentual_usado, percentual_disponivel).
               Retorna (None, None) se o caminho for inválido ou o espaço total for zero.
    """
    total, used, free = get_disk_space(path)

    # Verifica se os dados são válidos e se o total é maior que zero para evitar divisão por zero
    if total is None or total == 0:
        return (None, None)

    # Calcula as porcentagens
    percentage_used = (used / total) * 100
    percentage_free = (free / total) * 100

    return (percentage_used, percentage_free)


# --- Função Auxiliar para Exibir as Porcentagens ---

def show_disk_usage_percentages(path):
    """
    Exibe a porcentagem de espaço em disco usado e disponível para um caminho.

    Args:
        path (str): O caminho do sistema de arquivos a ser verificado.
    """
    percentage_used, percentage_free = get_disk_usage_percentages(path)

    if percentage_used is not None:
        print(f"Análise Percentual para o ponto de montagem de: '{path}'")
        print(f"  - Percentual de Uso: {percentage_used:.2f}%")
        print(f"  - Percentual Disponível: {percentage_free:.2f}%")
    else:
        # A função get_disk_space já emite um aviso, então esta parte é opcional
        print(f"Não foi possível calcular as porcentagens para '{path}'.")


# --- Exemplo de Uso ---
if __name__ == "__main__":
    
    print("--- Exemplo 1: Verificando as porcentagens do diretório raiz ('/') ---")
    show_disk_usage_percentages('/')
    
    print("\n" + "="*50 + "\n")
    
    # ---
    
    home_path = os.path.expanduser("~")
    print(f"--- Exemplo 2: Verificando as porcentagens do diretório home ('{home_path}') ---")
    show_disk_usage_percentages(home_path)

    print("\n" + "="*50 + "\n")

    # ---

    print("--- Exemplo 3: Tentando verificar um caminho inválido ---")
    show_disk_usage_percentages('/caminho/com/certeza/invalido')
