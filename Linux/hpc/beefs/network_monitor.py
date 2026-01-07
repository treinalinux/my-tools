#!/usr/bin/env python3
# name.........: network_monitor
# description..: Network Monitor
# author.......: Alan da Silva Alves
# version......: 1.0.0
# date.........: 1/7/2026
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
import os
import sys
import argparse


def check_permissions():
    if os.geteuid() != 0:
        print("ERRO: Execute como root (sudo) para acessar diagnósticos de hardware.")
        sys.exit(1)


def get_detailed_hw_stats(interface_name):
    """
    Tenta usar o 'ethtool -S' para pegar contadores específicos de hardware.
    Retorna um dicionário com os erros mais comuns.
    """
    stats = {
        'crc_errors': 0,    # Problema físico/cabo/interferência
        'missed_errors': 0, # Buffer cheio/CPU lenta
        'frame_errors': 0,  # Cabo ou Duplex
        'length_errors': 0, # MTU incorreto
        'collisions': 0     # Duplex incorreto
    }
    
    try:
        # Verifica se ethtool existe e roda
        stream = os.popen(f"ethtool -S {interface_name} 2>/dev/null")
        lines = stream.readlines()
        stream.close()

        for line in lines:
            parts = line.strip().split(':')
            if len(parts) != 2: continue
            
            key = parts[0].strip()
            try:
                value = int(parts[1].strip())
            except:
                continue

            # Mapeamento de nomes variados de drivers para chaves padrão
            if 'crc' in key: stats['crc_errors'] += value
            if 'missed' in key or 'drop' in key or 'fifo' in key: stats['missed_errors'] += value
            if 'frame' in key or 'align' in key: stats['frame_errors'] += value
            if 'length' in key or 'over' in key: stats['length_errors'] += value
            if 'collision' in key: stats['collisions'] += value
            
    except Exception:
        # Se falhar (ex: ethtool não instalado ou interface virtual), retorna zerado
        pass

    return stats


def get_interface_basic_stats(interface_name):
    """Lê o básico do /proc/net/dev"""
    try:
        stream = os.popen(f"grep {interface_name}: /proc/net/dev")
        line = stream.read()
        stream.close()
        
        if not line: return None

        data = line.split()
        # Ajuste de índice pois o split remove espaços.
        # Nome: (1)RX_bytes (2)packets (3)errs (4)drop ...
        # Se o nome estiver colado "eth0:", o indice muda.
        
        # Tratamento robusto para parsing
        raw_values = line.split(':')[1].split()
        
        return {
            'rx_err': int(raw_values[2]),
            'rx_drop': int(raw_values[3]),
            'tx_err': int(raw_values[10]),
            'tx_drop': int(raw_values[11])
        }
    except:
        return None

  
def analyze_capture_output(output_lines):
    """Analisa o texto do tcpdump em busca de pistas lógicas."""
    findings = {
        'bad_checksum': False,
        'unreachable': False,
        'tcp_reset': False,
        'arp_storm': False
    }
    
    arp_count = 0
    for line in output_lines:
        if "bad cksum" in line: findings['bad_checksum'] = True
        if "unreachable" in line: findings['unreachable'] = True
        if "Flags [R" in line: findings['tcp_reset'] = True
        if "ARP," in line: arp_count += 1
    
    if arp_count > 10: findings['arp_storm'] = True
    
    return findings


def diagnose_issues(interface_name, basic_delta, hw_stats_delta, capture_findings):
    """
    O CÉREBRO DO SCRIPT:
    Cruza dados de contadores e tcpdump para gerar recomendações.
    """
    recommendations = []
    
    # 1. Análise de Interface Wireless (baseado no nome)
    is_wireless = "wl" in interface_name
    
    # 2. Análise de Erros Físicos (RX Errors)
    if basic_delta['rx_err'] > 0:
        msg = f"[CRÍTICO] Detectados {basic_delta['rx_err']} erros de recebimento (RX)."
        
        if is_wireless:
            recommendations.append(f"{msg} -> Em Wi-Fi, isso geralmente é interferência ou sinal ruim.")
            recommendations.append("   AÇÃO: Verifique 'iwconfig'. Se o sinal for bom, desligue o Power Management (iwconfig wlan0 power off).")
            recommendations.append("   AÇÃO: Mude o canal do roteador Wi-Fi.")
        else:
            # Rede Cabeada
            if hw_stats_delta['crc_errors'] > 0:
                recommendations.append(f"{msg} -> O contador CRC subiu. O pacote chegou corrompido.")
                recommendations.append("   AÇÃO: TROQUE O CABO DE REDE imediatamente.")
                recommendations.append("   AÇÃO: Verifique a porta do Switch e conectores RJ45 oxidados.")
            elif hw_stats_delta['length_errors'] > 0:
                recommendations.append(f"{msg} -> Erros de tamanho (Length/Over).")
                recommendations.append("   AÇÃO: Verifique configurações de MTU (Jumbo Frames). O Switch e o Servidor devem ter o mesmo MTU.")
            elif hw_stats_delta['frame_errors'] > 0:
                 recommendations.append(f"{msg} -> Erros de Frame/Alinhamento.")
                 recommendations.append("   AÇÃO: Verifique incompatibilidade de Duplex (Full/Half) entre Switch e Servidor.")
            else:
                recommendations.append(f"{msg} -> Falha genérica de hardware.")
                recommendations.append("   AÇÃO: Teste outro cabo e outra porta do switch.")

    # 3. Análise de Descartados (Drops)
    if basic_delta['rx_drop'] > 0:
        recommendations.append(f"[ALERTA] {basic_delta['rx_drop']} pacotes descartados (Dropped) pelo Kernel.")
        recommendations.append("   DIAGNÓSTICO: O pacote chegou íntegro, mas o Linux o descartou.")
        recommendations.append("   CAUSA 1: Firewall (iptables/nftables) bloqueando pacotes silenciosamente?")
        recommendations.append("   CAUSA 2: Sobrecarga de CPU/Buffer. O servidor não conseguiu processar a tempo.")
        recommendations.append("   AÇÃO: Verifique logs do sistema e consumo de CPU (top/htop).")

    # 4. Análise Lógica (TCPDUMP)
    if capture_findings['bad_checksum']:
        recommendations.append("[REDE] 'Bad Checksum' detectado no tcpdump.")
        recommendations.append("   NOTA: Se for em pacotes de SAÍDA (TX), é normal (Offload). Se for ENTRADA (RX), confirma problema de cabo/driver.")
    
    if capture_findings['tcp_reset']:
        recommendations.append("[APLICAÇÃO] Muitos 'TCP Reset' detectados.")
        recommendations.append("   DIAGNÓSTICO: Conexões estão sendo recusadas ativamente.")
        recommendations.append("   AÇÃO: Verifique se o serviço/aplicação está rodando na porta correta ou se o Firewall está enviando REJECT.")

    if not recommendations and (basic_delta['rx_err'] + basic_delta['tx_err']) == 0:
        recommendations.append("[OK] A interface parece saudável. Nenhum erro físico ou lógico grave detectado neste período.")

    return recommendations


def run_diagnostic_cycle(interface_name, duration):
    print(f"\n{'='*80}")
    print(f" INICIANDO DIAGNÓSTICO AVANÇADO: {interface_name}")
    print(f" Duração do teste: {duration} segundos")
    print(f"{'='*80}")

    # --- FASE 1: Leitura Inicial ---
    print("-> Coletando estatísticas iniciais...")
    start_basic = get_interface_basic_stats(interface_name)
    start_hw = get_detailed_hw_stats(interface_name)
    
    if not start_basic:
        print("Erro: Interface não encontrada ou inativa.")
        return

    # --- FASE 2: Captura (TCPDUMP) ---
    print("-> Analisando tráfego em tempo real (Aguarde)...")
    # Captura silenciosa para análise interna, sem encher a tela
    cmd = f"timeout {duration} tcpdump -i {interface_name} -nn -v 2>&1"
    stream = os.popen(cmd)
    capture_lines = stream.readlines()
    stream.close()
    
    capture_analysis = analyze_capture_output(capture_lines)

    # --- FASE 3: Leitura Final e Deltas ---
    end_basic = get_interface_basic_stats(interface_name)
    end_hw = get_detailed_hw_stats(interface_name)

    # Calculando diferenças (O que aconteceu AGORA)
    delta_basic = {k: end_basic[k] - start_basic[k] for k in start_basic}
    delta_hw = {k: end_hw[k] - start_hw[k] for k in start_hw}

    # --- FASE 4: O Veredito ---
    print(f"\n{' RESULTADOS DO TESTE ':=^80}")
    
    # Exibir Contadores Relevantes
    total_errs = delta_basic['rx_err'] + delta_basic['tx_err']
    print(f"Erros Físicos Totais (RX+TX): {total_errs}")
    print(f"Pacotes Descartados (Drops):  {delta_basic['rx_drop']}")
    
    if total_errs > 0:
        print(f"\n--- Detalhes de Hardware (Ethtool) ---")
        for k, v in delta_hw.items():
            if v > 0: print(f" > {k}: +{v}")

    print(f"\n--- Recomendações do Sistema ---")
    recommendations = diagnose_issues(interface_name, delta_basic, delta_hw, capture_analysis)
    
    for rec in recommendations:
        print(rec)
    
    print(f"{'='*80}\n")


def main():
    check_permissions()
    parser = argparse.ArgumentParser(description="Network Doctor (RHEL8) - Diagnóstico e Recomendações")
    parser.add_argument('interfaces', nargs='*', help='Interfaces para diagnosticar')
    parser.add_argument('-t', '--time', type=int, default=30, help='Tempo de análise (padrão: 30s)')
    args = parser.parse_args()

    targets = args.interfaces
    
    # Se não informar interface, busca automática
    if not targets:
        print("Modo Automático: Buscando interfaces com erros históricos...")
        # Lógica simplificada para pegar lista
        stream = os.popen('cat /proc/net/dev')
        lines = stream.readlines()[2:]
        stream.close()
        targets = []
        for line in lines:
            data = line.split()
            if not data: continue
            # Soma erros RX+TX e Drops
            errs = int(data[2]) + int(data[3]) + int(data[10]) + int(data[11])
            if errs > 0:
                targets.append(data[0].strip(':'))
        
        if not targets:
            print("Nenhuma interface com erros históricos encontrada. Use: sudo ./script.py <interface> para forçar.")
            return

    for iface in targets:
        run_diagnostic_cycle(iface, args.time)

if __name__ == "__main__":
    main()
