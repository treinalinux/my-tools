#!/usr/bin/env python3
# Alan da Silva Alves
# 23/07/2025
# -*- coding: utf-8 -*-

"""
Ferramenta de Validação de Saúde de Rede InfiniBand para RHEL 8.
(Versão ajustada para usar os.popen em vez de subprocess)

Este script verifica o estado, a conectividade e os contadores de erro
das interfaces InfiniBand (HCAs) instaladas no sistema.

Pré-requisitos:
  - O pacote 'infiniband-diags' deve estar instalado (`sudo dnf install infiniband-diags`).
  - O script deve ser executado com permissões suficientes para acessar
    as ferramentas de diagnóstico de IB (geralmente como root ou um usuário com privilégios).

Como usar:
  1. Salve este código como 'ib_health_check_popen.py'.
  2. Dê permissão de execução: chmod +x ib_health_check_popen.py
  3. Execute: sudo ./ib_health_check_popen.py
"""

import os
import sys
import re

# --- Configuração de Cores para o Terminal ---
class AnsiColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_ok(message):
    """Imprime uma mensagem de sucesso em verde."""
    print(f"  {AnsiColors.OKGREEN}[  OK  ]{AnsiColors.ENDC} {message}")

def print_fail(message):
    """Imprime uma mensagem de falha em vermelho."""
    print(f"  {AnsiColors.FAIL}[ FALHA ]{AnsiColors.ENDC} {message}")

def print_warn(message):
    """Imprime uma mensagem de aviso em amarelo."""
    print(f"  {AnsiColors.WARNING}[ AVISO ]{AnsiColors.ENDC} {message}")

def print_info(message):
    """Imprime uma mensagem informativa."""
    print(f"  {AnsiColors.OKBLUE}[ INFO ]{AnsiColors.ENDC} {message}")

def print_header(message):
    """Imprime um cabeçalho para uma seção."""
    print(f"\n{AnsiColors.HEADER}{AnsiColors.BOLD}--- {message} ---{AnsiColors.ENDC}")

def run_command(command):
    """
    Executa um comando no shell usando os.popen e retorna a saída combinada e o código de retorno.
    NOTA: stderr é redirecionado para stdout para que possamos capturar tudo.
    Retorna (saida_combinada, codigo_de_retorno).
    """
    try:
        # Redireciona stderr para stdout (2>&1) para capturar toda a saída
        command_with_redirect = f"{command} 2>&1"
        pipe = os.popen(command_with_redirect)
        
        # Lê toda a saída do comando
        combined_output = pipe.read()
        
        # O método close() fecha o pipe e retorna o status de saída do processo
        exit_status_raw = pipe.close()
        
        # Converte o status de saída bruto para um código de saída padrão (0-255)
        # Se o comando foi bem-sucedido, exit_status_raw é None ou 0
        if exit_status_raw is None:
            return_code = 0
        else:
            # Em sistemas Unix-like, o código de saída está no byte mais alto do status
            return_code = os.waitstatus_to_exitcode(exit_status_raw)

        return combined_output, return_code
    except Exception as e:
        # Captura exceções inesperadas durante a execução do popen
        return f"Erro ao executar o comando: {str(e)}", 1

def get_ib_devices():
    """
    Lista os dispositivos InfiniBand disponíveis no sistema.
    Usa o diretório /sys/class/infiniband por ser mais confiável.
    """
    ib_sysfs_path = '/sys/class/infiniband'
    if not os.path.isdir(ib_sysfs_path):
        return []
    try:
        return [dev for dev in os.listdir(ib_sysfs_path)]
    except OSError:
        return []

def check_link_state(device):
    """
    Verifica o estado do link e o estado físico da porta usando 'ibstat'.
    """
    print_info(f"Verificando estado do link para o dispositivo: {AnsiColors.BOLD}{device}{AnsiColors.ENDC}")
    
    command = f"ibstat {device}"
    output, ret_code = run_command(command)

    if ret_code != 0:
        print_fail(f"Não foi possível executar 'ibstat' para {device}.")
        # A mensagem de erro (antes em stderr) agora está na variável 'output'
        print_warn(f"Saída do comando: {output.strip()}")
        return False

    # Extrai o estado lógico e físico da porta usando expressões regulares da saída
    state_match = re.search(r"State:\s+(.*)", output)
    phys_state_match = re.search(r"Physical state:\s+(.*)", output)
    rate_match = re.search(r"Rate:\s+(.*)", output)
    
    # Valida estado lógico
    if state_match:
        state = state_match.group(1).strip()
        if state == "ACTIVE":
            print_ok(f"Estado do Link: {AnsiColors.BOLD}{state}{AnsiColors.ENDC}")
        else:
            print_fail(f"Estado do Link: {AnsiColors.BOLD}{state}{AnsiColors.ENDC} (Esperado: ACTIVE)")
    else:
        print_fail("Não foi possível determinar o Estado do Link.")

    # Valida estado físico
    if phys_state_match:
        phys_state = phys_state_match.group(1).strip()
        if phys_state == "LinkUp":
            print_ok(f"Estado Físico: {AnsiColors.BOLD}{phys_state}{AnsiColors.ENDC}")
        else:
            print_fail(f"Estado Físico: {AnsiColors.BOLD}{phys_state}{AnsiColors.ENDC} (Esperado: LinkUp)")
    else:
        print_fail("Não foi possível determinar o Estado Físico.")

    # Exibe a taxa de dados
    if rate_match:
        rate = rate_match.group(1).strip()
        print_info(f"Taxa de dados (Rate): {AnsiColors.BOLD}{rate}{AnsiColors.ENDC}")
    else:
        print_warn("Não foi possível determinar a Taxa de Dados (Rate).")

    return True

def check_error_counters(device, port=1):
    """
    Verifica contadores de erro críticos usando 'perfquery'.
    """
    print_info(f"Verificando contadores de erro para {device} (Porta {port})...")
    
    counters_to_check = [
        "SymbolErrorCounter", "LinkErrorRecoveryCounter", "LinkDownedCounter",
        "PortRcvErrors", "PortRcvRemotePhysicalErrors", "PortXmitDiscards",
        "PortRcvSwitchRelayErrors", "LinkIntegrityErrors", "VL15Dropped"
    ]
    
    command = f"perfquery {device} {port}"
    output, ret_code = run_command(command)
    
    if ret_code != 0:
        print_fail(f"Não foi possível executar 'perfquery' em {device} porta {port}.")
        print_warn(f"Saída do comando: {output.strip()}")
        return

    found_errors = False
    for line in output.splitlines():
        for counter in counters_to_check:
            if re.match(r"^\.*" + re.escape(counter), line.strip()):
                try:
                    value = int(line.split()[-1])
                    if value > 0:
                        print_warn(f"Contador {AnsiColors.BOLD}{counter}{AnsiColors.ENDC}: {AnsiColors.FAIL}{value}{AnsiColors.ENDC}")
                        found_errors = True
                except (ValueError, IndexError):
                    print_warn(f"Não foi possível analisar o valor para o contador: {counter}")
    
    if not found_errors:
        print_ok("Nenhum contador de erro crítico com valor elevado foi encontrado.")

def main():
    """Função principal que orquestra as verificações."""
    if os.geteuid() != 0:
        print_warn("Este script funciona melhor quando executado como root (ou com sudo).")
        print_warn("Alguns comandos de diagnóstico podem falhar sem privilégios elevados.\n")

    print_header("Iniciando Verificação de Saúde da Rede InfiniBand (usando os.popen)")

    devices = get_ib_devices()
    if not devices:
        print_fail("Nenhum dispositivo InfiniBand (HCA) encontrado no sistema.")
        print_fail("Verifique se os drivers estão carregados e se o hardware está presente.")
        sys.exit(1)

    print_info(f"Dispositivos encontrados: {', '.join(AnsiColors.BOLD + d + AnsiColors.ENDC for d in devices)}")

    for dev in devices:
        print_header(f"Analisando Dispositivo: {dev}")
        if not check_link_state(dev):
            continue
        check_error_counters(dev, port=1)

    print_header("Verificação Concluída")

if __name__ == "__main__":
    main()
