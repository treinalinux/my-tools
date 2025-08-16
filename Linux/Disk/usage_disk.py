import shutil
import os

#
# Alan Alves
# 
# Ferramentas para trabalhar com espaço em disco
# 

# --- Função Base (essencial para os cálculos) ---

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
        real_path = os.path.realpath(path)
        if not os.path.exists(real_path):
            # Usamos print para avisos, mas em uma aplicação maior, um log seria melhor.
            print(f"Aviso: O caminho '{path}' não existe.")
            return (None, None, None)
    except OSError as e:
        print(f"Aviso: Não foi possível verificar o caminho '{path}': {e}")
        return (None, None, None)

    total, used, free = shutil.disk_usage(real_path)
    return (total, used, free)


# --- Nova Função Reutilizável e Flexível ---

def get_disk_percentage(path, metric='used'):
    """
    Calcula uma porcentagem específica (de uso ou disponível) para o disco.

    Args:
        path (str): O caminho do sistema de arquivos a ser verificado.
        metric (str, optional): A métrica desejada. Aceita 'used' (em uso) ou 'free' (disponível).
                                O padrão é 'used'. O valor não diferencia maiúsculas/minúsculas.

    Returns:
        float: A porcentagem solicitada, como um número de ponto flutuante (ex: 75.4).
               Retorna None se a métrica for inválida ou se não for possível ler o disco.
    """
    total, used, free = get_disk_space(path)

    # Validação para evitar erros de cálculo
    if total is None or total == 0:
        return None

    # Normaliza o argumento da métrica para minúsculas para torná-lo flexível
    metric_lower = metric.lower()

    if metric_lower == 'used':
        return (used / total) * 100
    elif metric_lower == 'free':
        return (free / total) * 100
    else:
        print(f"Erro: Métrica '{metric}' inválida. Use 'used' ou 'free'.")
        return None


# --- Exemplo de Uso Prático da Nova Função ---
if __name__ == "__main__":

    path_to_check = '/' # Vamos verificar o diretório raiz
    
    print(f"--- Verificando informações para o caminho: '{path_to_check}' ---")

    # ---
    # Cenário 1: Quero saber a porcentagem EM USO
    print("\n1. Solicitando a porcentagem de USO:")
    
    # Chama a função pedindo a métrica 'used'
    used_percentage = get_disk_percentage(path_to_check, metric='used')
    
    if used_percentage is not None:
        # Formata a saída para o usuário final
        print(f"   => A porcentagem de espaço em uso é: {used_percentage:.2f}%")
    else:
        print("   => Não foi possível obter a informação.")

    # ---
    # Cenário 2: Quero saber a porcentagem DISPONÍVEL
    print("\n2. Solicitando a porcentagem DISPONÍVEL:")
    
    # Chama a função pedindo a métrica 'free'
    free_percentage = get_disk_percentage(path_to_check, metric='free')

    if free_percentage is not None:
        print(f"   => A porcentagem de espaço disponível é: {free_percentage:.2f}%")
    else:
        print("   => Não foi possível obter a informação.")

    # ---
    # Cenário 3: Usando o valor padrão (que é 'used')
    print("\n3. Solicitando sem especificar a métrica (padrão 'used'):")
    
    default_percentage = get_disk_percentage(path_to_check)
    
    if default_percentage is not None:
        print(f"   => O resultado padrão (uso) é: {default_percentage:.2f}%")
    else:
        print("   => Não foi possível obter a informação.")
        
    # ---
    # Cenário 4: Testando uma métrica inválida
    print("\n4. Testando com uma métrica inválida:")
    
    invalid_metric = get_disk_percentage(path_to_check, metric='total') # 'total' não é uma opção válida
    
    if invalid_metric is None:
        print("   => A função retornou 'None' como esperado para métricas inválidas.")
