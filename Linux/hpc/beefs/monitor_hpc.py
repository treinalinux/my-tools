#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitora a saúde de um nó de cluster HPC, gerando relatórios em HTML e CSV.

Versão: 3.0.3

Este script é uma ferramenta de linha de comando projetada para ser executada em
nós de computação ou de gerenciamento de um cluster de alta performance (HPC).
Ele realiza uma série de verificações de hardware e software, classifica os
resultados e, opcionalmente, gera um relatório HTML detalhado se encontrar
problemas ou se forçado pelo usuário.

Funcionalidades Principais:
  - Verificação de Recursos: CPU, Memória, Load Average.
  - Saúde de Hardware: Status de GPUs NVIDIA, saúde de discos (S.M.A.R.T.),
    logs do kernel (dmesg).
  - Rede de Alta Performance: Estado, contadores de erro e topologia de
    portas InfiniBand.
  - Serviços Essenciais: Checa o status de serviços definidos pelo usuário.
  - Lógica Inteligente: Detecta ambientes com Bright Cluster Manager e Pacemaker
    para evitar falsos alarmes em serviços gerenciados pelo cluster.
  - Armazenamento: Monitora o uso de partições BeeGFS (individual e agregado).
  - Relatórios: Saída em log CSV e relatórios HTML com base em templates.

Uso via Linha de Comando:
  - Execução padrão:
    $ python3 monitor_hpc.py

  - Forçar geração de relatório HTML (mesmo sem problemas):
    $ python3 monitor_hpc.py --force-html

  - Verificar discos S.M.A.R.T. específicos:
    $ python3 monitor_hpc.py --smart-disks /dev/sda,/dev/nvme0n1

  - Gerar um relatório de teste com dados de exemplo:
    $ python3 monitor_hpc.py --test-html

Estrutura de Arquivos Necessária:
.
├── monitor_hpc.py
├── update_kb.py
├── data/
│   ├── knowledge_base.json
│   └── test_data.json
└── templates/
    └── report_template.html
"""

import csv
import datetime
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# --- CONSTANTES ---
STATUS_NORMAL = 'NORMAL'
STATUS_WARN = 'ATENÇÃO'
STATUS_FAIL = 'FALHA'
PRIORITY_CRITICAL = 'P1 (Crítica)'
PRIORITY_HIGH = 'P2 (Alta)'
PRIORITY_MEDIUM = 'P3 (Média)'
PRIORITY_INFO = 'P4 (Informativa)'


class Config:
    """Agrupa todas as configurações e thresholds do script."""
    CPU_THRESHOLD_WARN, MEM_THRESHOLD_WARN, LOAD_AVERAGE_RATIO_WARN = 85.0, 85.0, 1.5
    SSD_PERCENTAGE_USED_THRESHOLD_WARN, SSD_TEMPERATURE_THRESHOLD_WARN = 85.0, 70
    GPU_TEMP_THRESHOLD_WARN, GPU_UTIL_THRESHOLD_WARN = 85.0, 90.0
    BEEGFS_USAGE_THRESHOLD_WARN = 90.0
    COMMON_SERVICES: List[str] = [
        'chronyd', 'nfs-server', 'cmdaemon', 'mysql', 'mariadb'
    ]
    BCM_HEAD_NODE_SERVICES: List[str] = [
        'dhcpd', 'named', 'cmd', 'corosync', 'pacemaker', 'pcsd'
    ]
    BCM_ACTIVE_MASTER_SERVICES: List[str] = [
        'grafana-server', 'influxdb', 'beegfs-mon'
    ]
    INTERFACES_TO_IGNORE = ['lo', 'virbr']
    PACEMAKER_MANAGED_SERVICES = ['beegfs-storage', 'beegfs-meta']
    SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
    OUTPUT_DIR = os.path.join(os.getcwd(), 'report')
    CSV_LOG_FILE, HTML_REPORT_FILE = (
        os.path.join(OUTPUT_DIR, 'hpc_monitoring_log.csv'),
        os.path.join(OUTPUT_DIR, 'hpc_status_report.html')
    )
    KB_FILE, TEMPLATE_FILE = (
        os.path.join(SCRIPT_DIR, 'data', 'knowledge_base.json'),
        os.path.join(SCRIPT_DIR, 'templates', 'report_template.html')
    )
    HARDWARE_ERROR_KEYWORDS = [
        'error', 'fail', 'critical', 'fatal', 'segfault'
    ]


def run_command(command: str) -> Tuple[str, int]:
    """Executa um comando no shell e retorna sua saída e código de status."""
    pipe = os.popen(f'LC_ALL=C {command} 2>&1')
    output = pipe.read().strip()
    exit_status = pipe.close()
    code = 0
    if exit_status is not None:
        if os.WIFEXITED(exit_status):
            code = os.WEXITSTATUS(exit_status)
        else:
            code = 1
    return output, code


def format_bytes(size_kb: float) -> str:
    """Converte kilobytes para um formato legível (KB, MB, GB, TB, etc.)."""
    if size_kb == 0:
        return "0 KB"
    size_names = ("KB", "MB", "GB", "TB", "PB", "EB", "ZB")
    i, size = 0, float(size_kb)
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f} {size_names[i]}"


def load_knowledge_base(kb_file: str) -> Dict:
    """Carrega a base de conhecimento de um arquivo JSON."""
    if not os.path.exists(kb_file):
        return {}
    try:
        with open(kb_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def get_kb_suggestion(details: str, knowledge_base: Dict) -> Optional[str]:
    """Busca uma sugestão na base de conhecimento com base nos detalhes."""
    for category in knowledge_base.values():
        for keyword, suggestion in category.items():
            if keyword.lower() in details.lower():
                return suggestion
    return None


class BaseCheck:
    """Classe base abstrata para todas as verificações de monitoramento."""
    def __init__(self, config: Config):
        self.config, self.category, self.item = config, "N/A", "N/A"

    def execute(self) -> List[Dict[str, Any]]:
        """Método de execução principal para uma verificação."""
        raise NotImplementedError("Classes filhas devem implementar este método.")

    def _build_result(self, status: str, priority: str, details: str,
                      item: Optional[str] = None) -> Dict[str, Any]:
        """Constrói um dicionário de resultado padronizado."""
        return {
            'category': self.category, 'item': item or self.item,
            'status': status, 'priority': priority, 'details': details
        }


class CPUCheck(BaseCheck):
    """Verifica a utilização geral da CPU."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Recursos de Sistema", "Uso de CPU"

    def _get_cpu_times(self) -> Optional[Tuple[int, int]]:
        """Lê e retorna os tempos totais e ociosos da CPU do /proc/stat."""
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            parts, cpu_times = line.split(), [int(p) for p in line.split()[1:9]]
            return sum(cpu_times), cpu_times[3]
        except (IOError, IndexError, ValueError):
            return None

    def execute(self) -> List[Dict[str, Any]]:
        """Calcula o uso da CPU em um intervalo de 1 segundo."""
        t1 = self._get_cpu_times()
        if not t1:
            return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, "Não foi possível ler /proc/stat.")]
        time.sleep(1)
        t2 = self._get_cpu_times()
        if not t2:
            return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, "Não foi possível ler /proc/stat (2ª amostragem).")]
        delta_total, delta_idle = t2[0] - t1[0], t2[1] - t1[1]
        usage = 100.0 * (delta_total - delta_idle) / delta_total if delta_total > 0 else 0.0
        s, p, d = (
            (STATUS_WARN, PRIORITY_HIGH, f"Uso de {usage:.1f}% excede o limite.")
            if usage >= self.config.CPU_THRESHOLD_WARN else
            (STATUS_NORMAL, PRIORITY_INFO, f"Uso de {usage:.1f}%.")
        )
        return [self._build_result(s, p, d)]


class MemoryCheck(BaseCheck):
    """Verifica a utilização de memória RAM."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Recursos de Sistema", "Uso de Memória"

    def execute(self) -> List[Dict[str, Any]]:
        """Calcula o uso de memória real, desconsiderando caches."""
        try:
            mem_info = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mem_info[parts[0].rstrip(':')] = int(parts[1])
            mem_total = mem_info['MemTotal']
            mem_used = (mem_total - mem_info['MemFree'] - mem_info['Buffers'] -
                        mem_info['Cached'] - mem_info.get('SReclaimable', 0))
            mem_usage = (mem_used / mem_total) * 100.0 if mem_total > 0 else 0.0
            s, p, d = (
                (STATUS_WARN, PRIORITY_HIGH, f"Uso de {mem_usage:.1f}% excede o limite.")
                if mem_usage >= self.config.MEM_THRESHOLD_WARN else
                (STATUS_NORMAL, PRIORITY_INFO, f"Uso de {mem_usage:.1f}%.")
            )
            return [self._build_result(s, p, d)]
        except (IOError, KeyError, ValueError) as e:
            return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, f"Não foi possível ler /proc/meminfo. Erro: {e}")]


class LoadAverageCheck(BaseCheck):
    """Verifica a média de carga (load average) do sistema."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Recursos de Sistema", "Média de Carga"

    def execute(self) -> List[Dict[str, Any]]:
        """Compara a carga de 1 minuto com o número de núcleos da CPU."""
        try:
            with open('/proc/loadavg', 'r') as f:
                load_1m_str, load_5m_str, load_15m_str = f.read().split()[:3]
            load_1m = float(load_1m_str)
            nproc_out, nproc_code = run_command("nproc")
            num_cores = int(nproc_out) if nproc_code == 0 and nproc_out.isdigit() else 1
            load_ratio = load_1m / num_cores
            d = (f"Carga (1m, 5m, 15m): {load_1m_str}, {load_5m_str}, "
                 f"{load_15m_str} ({num_cores} núcleos).")
            s, p = (
                (STATUS_WARN, PRIORITY_HIGH)
                if load_ratio >= self.config.LOAD_AVERAGE_RATIO_WARN else
                (STATUS_NORMAL, PRIORITY_INFO)
            )
            if s == STATUS_WARN:
                d += f" Carga de 1 minuto ({load_1m}) é alta para os núcleos."
            return [self._build_result(s, p, d)]
        except (IOError, ValueError) as e:
            return [self._build_result(STATUS_FAIL, PRIORITY_HIGH, f"Não foi possível ler /proc/loadavg. Erro: {e}")]


class GPUCheck(BaseCheck):
    """Verifica o estado de GPUs NVIDIA."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Recursos de GPU", "Status das GPUs"

    def execute(self) -> List[Dict[str, Any]]:
        """Usa nvidia-smi para obter temperatura, uso e memória das GPUs."""
        _, code = run_command("nvidia-smi -L")
        if code != 0:
            return []
        query = "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total"
        output, code = run_command(
            f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits"
        )
        if code != 0:
            return [self._build_result(STATUS_FAIL, PRIORITY_HIGH, f"Falha ao executar nvidia-smi. Saída: {output}")]
        results = []
        for line in output.splitlines():
            try:
                idx, name, temp, util, mem_used, mem_total = \
                    [p.strip() for p in line.split(',')]
                temp, util, mem_used, mem_total = \
                    float(temp), float(util), float(mem_used), float(mem_total)
                mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                item_name = f'GPU {idx}: {name}'
                status, warnings = STATUS_NORMAL, []
                if temp >= self.config.GPU_TEMP_THRESHOLD_WARN:
                    status = STATUS_WARN
                    warnings.append(f"Temp: {temp}°C (limite: {self.config.GPU_TEMP_THRESHOLD_WARN}°C)")
                if util >= self.config.GPU_UTIL_THRESHOLD_WARN:
                    status = STATUS_WARN
                    warnings.append(f"Uso: {util}% (limite: {self.config.GPU_UTIL_THRESHOLD_WARN}%)")
                p, d = (
                    (PRIORITY_HIGH, ", ".join(warnings)) if status == STATUS_WARN else
                    (PRIORITY_INFO, f"Temp: {temp}°C, Uso: {util}%, Memória: "
                                    f"{mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%)")
                )
                results.append(self._build_result(status, p, d, item=item_name))
            except (ValueError, IndexError):
                results.append(self._build_result(STATUS_FAIL, PRIORITY_HIGH, f'Falha ao analisar linha: "{line}"'))
        return results


class InfinibandCheck(BaseCheck):
    """Verifica a saúde completa da rede InfiniBand."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Rede de Alta Performance", "Saúde do InfiniBand"

    def _check_error_counters(self, dev_name: str, port: str) -> List[str]:
        """Lê contadores de erro do InfiniBand diretamente do /sys."""
        counters = ['symbol_error', 'link_error_recovery', 'link_downed', 'port_rcv_errors', 'port_xmit_discards']
        errors = []
        path = f"/sys/class/infiniband/{dev_name}/ports/{port}/counters"
        if not os.path.isdir(path):
            return []
        for c_name in counters:
            try:
                with open(os.path.join(path, c_name), 'r') as f:
                    val = int(f.read().strip())
                if val > 0:
                    errors.append(f"{c_name.replace('_', ' ').title()}: {val}")
            except (IOError, ValueError):
                continue
        return errors

    def execute(self) -> List[Dict[str, Any]]:
        """Executa a verificação multi-etapas do InfiniBand."""
        _, code = run_command("ibstat -V")
        if code != 0:
            return []
        ibstat_out, code = run_command("ibstat")
        if code != 0:
            return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, f"Falha ao executar 'ibstat'. Saída: {ibstat_out}")]
        results, local_ports, has_ib, has_active_ib = [], {}, False, False
        for block in ibstat_out.split('CA \'')[1:]:
            lines, ca_name = block.splitlines(), block.splitlines()[0].split('\'')[0]
            ports, cur_port = {}, None
            for line in lines[1:]:
                clean = line.strip()
                if clean.startswith('Port ') and clean.endswith(':'):
                    cur_port = clean.split(':')[0]
                    if cur_port not in ports:
                        ports[cur_port] = {}
                elif ':' in line and cur_port:
                    key, val = line.split(':', 1)
                    ports[cur_port][key.strip()] = val.strip()
            for p_key, details in ports.items():
                guid = details.get('Port GUID', 'N/A')
                local_ports[guid] = {'ca': ca_name, 'port': p_key, 'details': details, 'conn': None}
                p_num, layer = p_key.split()[-1], details.get('Link layer', 'N/A')
                state, p_state = details.get('State', 'N/A'), details.get('Physical state', 'N/A')
                rate = details.get('Rate', 'N/A')
                item = f"{ca_name} - {p_key}"
                if layer == 'InfiniBand':
                    has_ib = True
                    if state == 'Active' and p_state == 'LinkUp':
                        has_active_ib = True
                        errors = self._check_error_counters(ca_name, p_num)
                        if errors:
                            d = f"Link Ativo, mas com erros. Taxa: {rate}. Contadores: {', '.join(errors)}."
                            results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, d, item=item))
                elif layer == 'Ethernet' and (state != 'Active' or p_state != 'LinkUp'):
                    d = f"Interface Ethernet sobre IB inativa. Estado: {state}, Físico: {p_state}, Taxa: {rate}"
                    results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, d, item=item))
        if has_ib and not has_active_ib:
            d = "Foram detectadas placas InfiniBand, mas todas as portas estão inativas. Este pode ser o comportamento esperado para este nó."
            results.append(self._build_result(STATUS_WARN, PRIORITY_INFO, d))
            return results
        if not has_active_ib:
            return results
        iblink_out, code = run_command("iblinkinfo")
        if code != 0:
            results.append(self._build_result(
                STATUS_WARN, PRIORITY_MEDIUM, "Não foi possível executar 'iblinkinfo' para verificar as conexões."))
            return results
        for line in iblink_out.splitlines():
            for guid, p_info in local_ports.items():
                if guid in line and '==>' in line:
                    match = re.search(r'==>\s+(\d+)\s+(\d+)\[\s*\]\s+"([^"]+)"', line)
                    if match:
                        p_info['conn'] = {
                            'lid': match.group(1), 'port': match.group(2), 'name': match.group(3).strip()
                        }
                    break
        conn_details, all_connected = [], True
        for guid, p_info in local_ports.items():
            details = p_info['details']
            is_active_ib = (details.get('Link layer') == 'InfiniBand' and
                            details.get('State') == 'Active' and
                            details.get('Physical state') == 'LinkUp')
            if not is_active_ib:
                continue
            if p_info['conn']:
                lid, rate = details.get('Base lid', 'N/A'), details.get('Rate', 'N/A')
                p_name, p_port = p_info['conn']['name'].split('"')[0].strip(), p_info['conn']['port']
                conn_details.append(
                    f"  • {p_info['ca']}/{p_info['port'].split()[-1]} (LID: {lid}, Taxa: {rate}Gbps) -> {p_name} (Porta: {p_port})"
                )
            else:
                all_connected = False
                item = f"{p_info['ca']} - {p_info['port']}"
                results.append(self._build_result(
                    STATUS_FAIL, PRIORITY_CRITICAL, "Porta ativa mas sem conexão detectada (verificado com iblinkinfo).", item=item))
        if has_active_ib and all_connected and not any(r['status'] == STATUS_FAIL for r in results):
            details = "Todas as portas InfiniBand estão ativas, sem erros e conectadas:<br>" + "<br>".join(conn_details)
            if conn_details:
                results.insert(0, self._build_result(
                    STATUS_NORMAL, PRIORITY_INFO, details, item="Resumo da Conexão InfiniBand"))
        return results


class NetworkErrorCheck(BaseCheck):
    """Verifica contadores de erro em interfaces de rede padrão."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Saúde da Rede", "Erros de Interface de Rede"

    def execute(self) -> List[Dict[str, Any]]:
        """Lê /proc/net/dev e procura por pacotes com erro ou descartados."""
        try:
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()[2:]
        except IOError:
            return [self._build_result(STATUS_FAIL, PRIORITY_MEDIUM, "Não foi possível ler /proc/net/dev.")]
        results = []
        for line in lines:
            try:
                parts = line.split()
                interface = parts[0].strip(':')
                if any(interface.startswith(p) for p in self.config.INTERFACES_TO_IGNORE):
                    continue
                rx_errs, rx_drop = int(parts[3]), int(parts[4])
                tx_errs, tx_drop = int(parts[11]), int(parts[12])
                if (rx_errs + tx_errs) > 0 or (rx_drop + tx_drop) > 0:
                    d = (f"Erros: {rx_errs + tx_errs} (RX:{rx_errs}, TX:{tx_errs}), "
                         f"Descartados: {rx_drop + tx_drop} (RX:{rx_drop}, TX:{tx_drop})")
                    results.append(self._build_result(
                        STATUS_WARN, PRIORITY_MEDIUM, d, item=f'Interface {interface}'))
            except (ValueError, IndexError):
                continue
        if not results:
            results.append(self._build_result(
                STATUS_NORMAL, PRIORITY_INFO, "Nenhum erro ou pacote descartado encontrado."))
        return results


class DiskHealthCheck(BaseCheck):
    """Verifica a saúde S.M.A.R.T. de discos."""
    def __init__(self, config: Config, disks_to_check: List[str]):
        super().__init__(config)
        self.category = "Saúde dos Discos (S.M.A.R.T.)"
        self.disks_to_check = disks_to_check

    def execute(self) -> List[Dict[str, Any]]:
        """Executa smartctl para cada disco especificado na linha de comando."""
        _, code = run_command("smartctl -V")
        if code != 0:
            return [self._build_result(
                STATUS_FAIL, PRIORITY_MEDIUM, "A ferramenta 'smartctl' não foi encontrada.",
                item="Ferramenta smartctl")]
        results = []
        for disk_arg in self.disks_to_check:
            path, type_arg = disk_arg, ""
            if ':' in disk_arg:
                path, type_ = disk_arg.split(':', 1)
                type_arg = f"-d {type_}"
            item = f"Disco {path}"
            out, _ = run_command(f"smartctl -H {type_arg} {path}")
            s, p, d = (
                STATUS_FAIL, PRIORITY_HIGH,
                f"Não foi possível determinar o estado S.M.A.R.T. Saída: {out}"
            )
            if "PASSED" in out:
                s, p, d = STATUS_NORMAL, PRIORITY_INFO, "O teste de autoavaliação S.M.A.R.T. foi aprovado."
            elif "FAILED" in out:
                s, p, d = STATUS_FAIL, PRIORITY_CRITICAL, "O teste S.M.A.R.T. FALHOU. Recomenda-se a substituição do disco."
            elif "Disabled" in out:
                s, p, d = STATUS_WARN, PRIORITY_MEDIUM, "O suporte a S.M.A.R.T. está desativado."
            if s == STATUS_NORMAL:
                is_ssd, _ = run_command(f"cat /sys/block/{os.path.basename(path)}/queue/rotational")
                if is_ssd.strip() == '0':
                    warnings = self._check_ssd_attributes(path, type_arg)
                    if warnings:
                        s, p = STATUS_WARN, PRIORITY_HIGH
                        d += " " + " ".join(warnings)
            results.append(self._build_result(s, p, d, item=item))
        return results

    def _check_ssd_attributes(self, path: str, type_arg: str) -> List[str]:
        """Verifica atributos específicos de desgaste e temperatura de SSDs."""
        out, _ = run_command(f"smartctl -A {type_arg} {path}")
        warnings = []
        for line in out.splitlines():
            try:
                if "Percentage Used" in line:
                    used = float(line.split()[-1])
                    if used >= self.config.SSD_PERCENTAGE_USED_THRESHOLD_WARN:
                        warnings.append(f"Desgaste ({used}%) excede o limite.")
                elif "Temperature_Celsius" in line:
                    temp = int(line.split()[-1])
                    if temp >= self.config.SSD_TEMPERATURE_THRESHOLD_WARN:
                        warnings.append(f"Temperatura ({temp}°C) excede o limite.")
            except (ValueError, IndexError):
                continue
        return warnings


class ServicesCheck(BaseCheck):
    """Verifica o status de serviços essenciais, com lógica para BCM e Pacemaker."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Serviços Essenciais", "Status dos Serviços"

    def execute(self) -> List[Dict[str, Any]]:
        """Verifica serviços, filtrando-os com base na função do nó."""
        results, services_to_verify = [], []
        bcm_role = "Nó Comum"
        output, code = run_command("cmha status")
        is_bcm_head_node = code == 0 and output
        if is_bcm_head_node:
            first_line = output.splitlines()[0]
            if "running in active mode" in first_line:
                bcm_role = "BCM Master Ativo"
            elif "running in passive mode" in first_line:
                bcm_role = "BCM Master Passivo"
            else:
                bcm_role = "BCM Head Node (Estado Desconhecido)"
                d = f"O serviço cmha está em um estado inesperado. Saída: {first_line}"
                results.append(self._build_result(STATUS_WARN, PRIORITY_HIGH, d, item="Estado do CMHA"))
        if bcm_role == "Nó Comum":
            services_to_verify = list(self.config.COMMON_SERVICES)
            _, pacemaker_code = run_command("systemctl is-active pacemaker")
            if pacemaker_code == 0:
                managed = ", ".join(self.config.PACEMAKER_MANAGED_SERVICES)
                d = f"Pacemaker ativo. Serviços ({managed}) são gerenciados pelo cluster e ignorados aqui."
                results.append(self._build_result(STATUS_NORMAL, PRIORITY_INFO, d, item="Gerenciamento via Pacemaker"))
                services_to_verify = [s for s in services_to_verify if s not in self.config.PACEMAKER_MANAGED_SERVICES]
        else:
            d = f"Nó detectado como {bcm_role}. Verificando serviços específicos para esta função."
            results.append(self._build_result(STATUS_NORMAL, PRIORITY_INFO, d, item="Detecção de Função BCM"))
            services_to_verify = list(self.config.COMMON_SERVICES) + list(self.config.BCM_HEAD_NODE_SERVICES)
            if bcm_role == "BCM Master Ativo":
                services_to_verify.extend(self.config.BCM_ACTIVE_MASTER_SERVICES)
        for service in sorted(list(set(services_to_verify))):
            output, _ = run_command(f"systemctl status {service}")
            if "Loaded: not-found" in output or "could not be found" in output:
                continue
            item_name = f'Serviço: {service}'
            if "Active: active (running)" in output:
                s, p, d = STATUS_NORMAL, PRIORITY_INFO, f'O serviço {service} está ativo.'
            else:
                s, p = STATUS_FAIL, PRIORITY_CRITICAL
                d = (f'O serviço {service} está inativo ou em falha.\nDetalhes:\n' + "\n".join(output.splitlines()[-5:]))
            results.append(self._build_result(s, p, d, item=item_name))
        return results


class DmesgCheck(BaseCheck):
    """Verifica os logs do kernel (dmesg) por erros de hardware."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Hardware e S.O.", "Logs do Kernel (dmesg)"

    def execute(self) -> List[Dict[str, Any]]:
        """Usa grep para encontrar palavras-chave de erro no dmesg."""
        keys = '|'.join(self.config.HARDWARE_ERROR_KEYWORDS)
        out, code = run_command(f"dmesg | grep -iE '({keys})'")
        if code == 0 and out:
            s, p, d = STATUS_WARN, PRIORITY_HIGH, f"Possíveis erros de hardware encontrados:\n{out}"
        elif "Operation not permitted" in out:
            s, p, d = STATUS_WARN, PRIORITY_MEDIUM, "Não foi possível ler logs do kernel. Execute com 'sudo'."
        else:
            s, p, d = STATUS_NORMAL, PRIORITY_INFO, "Nenhum erro crítico recente encontrado."
        return [self._build_result(s, p, d)]


class BeeGFSDiskCheck(BaseCheck):
    """Verifica o uso de disco em pontos de montagem BeeGFS."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category, self.item = "Uso de Disco BeeGFS", "Uso das Partições"

    def _find_beegfs_mounts(self) -> List[str]:
        """Encontra todos os pontos de montagem que começam com /BeeGFS."""
        mounts, output, code = [], *run_command("mount")
        if code != 0:
            return mounts
        for line in output.splitlines():
            if ' on /BeeGFS' in line:
                try:
                    mount_point = line.split(' on ')[1].split(' ')[0]
                    if mount_point.startswith('/BeeGFS'):
                        mounts.append(mount_point)
                except IndexError:
                    continue
        return sorted(list(set(mounts)))

    def execute(self) -> List[Dict[str, Any]]:
        """Calcula o uso individual e agregado das partições BeeGFS."""
        beegfs_mounts = self._find_beegfs_mounts()
        if not beegfs_mounts:
            return []
        results, total_size_kb, total_used_kb = [], 0, 0
        for mount in beegfs_mounts:
            output, code = run_command(f"df -k {mount}")
            if code != 0 or len(output.splitlines()) < 2:
                continue
            try:
                parts = output.splitlines()[1].split()
                size, used, avail, percent = int(parts[1]), int(parts[2]), int(parts[3]), float(parts[4].replace('%', ''))
                total_size_kb += size
                total_used_kb += used
                status, priority = (
                    (STATUS_WARN, PRIORITY_HIGH) if percent >= self.config.BEEGFS_USAGE_THRESHOLD_WARN
                    else (STATUS_NORMAL, PRIORITY_INFO)
                )
                details = (f"Uso: {percent:.1f}%. Total: {format_bytes(size)}, "
                           f"Usado: {format_bytes(used)}, Disponível: {format_bytes(avail)}.")
                results.append(self._build_result(
                    status, priority, details, item=f'Uso da Partição {mount}'))
            except (ValueError, IndexError):
                continue
        if total_size_kb > 0:
            agg_usage = (total_used_kb / total_size_kb) * 100.0
            agg_avail = total_size_kb - total_used_kb
            status, priority = (
                (STATUS_WARN, PRIORITY_HIGH) if agg_usage >= self.config.BEEGFS_USAGE_THRESHOLD_WARN
                else (STATUS_NORMAL, PRIORITY_INFO)
            )
            details = (f"Uso total: {agg_usage:.1f}%. Total: {format_bytes(total_size_kb)}, "
                       f"Usado: {format_bytes(total_used_kb)}, Disponível: {format_bytes(agg_avail)}.")
            results.append(self._build_result(
                status, priority, details, item='Uso Agregado das Partições'))
        return results


class UptimeCheck(BaseCheck):
    """Verifica o tempo de atividade (uptime) do servidor."""
    def __init__(self, config: Config):
        super().__init__(config)
        self.category = "Saúde do S.O."
        self.item = "Tempo de Atividade (Uptime)"

    def execute(self) -> List[Dict[str, Any]]:
        """Verifica se o servidor foi reiniciado nas últimas 24 horas."""
        output, code = run_command("uptime -s")
        if code != 0:
            return [self._build_result(
                STATUS_FAIL, PRIORITY_MEDIUM,
                f"Não foi possível obter o uptime. Saída: {output}"
            )]
        try:
            boot_time = datetime.datetime.strptime(output, '%Y-%m-%d %H:%M:%S')
            uptime_delta = datetime.datetime.now() - boot_time
            uptime_str = str(uptime_delta).split(".")[0]
            if uptime_delta.total_seconds() < 86400:  # 24 horas
                status, priority = STATUS_WARN, PRIORITY_MEDIUM
                details = f"O servidor foi reiniciado nas últimas 24 horas. Tempo ativo: {uptime_str}."
            else:
                status, priority = STATUS_NORMAL, PRIORITY_INFO
                details = f"O servidor está ativo há mais de 24 horas. Tempo ativo: {uptime_str}."
            return [self._build_result(status, priority, details)]
        except ValueError:
            return [self._build_result(
                STATUS_FAIL, PRIORITY_MEDIUM,
                f"Não foi possível analisar a data de boot: '{output}'"
            )]


class Monitor:
    """Orquestra todo o processo de monitoramento e geração de relatórios."""
    def __init__(self, args: Dict[str, Any]):
        """Inicializa o monitor."""
        self.args, self.config = args, Config()
        self.knowledge_base = load_knowledge_base(self.config.KB_FILE)
        self.hostname, _ = run_command("hostname")
        self.timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.scenario = self._determine_scenario(self.hostname)

    def _determine_scenario(self, hostname: str) -> str:
        """Determina o cenário com base no prefixo do hostname."""
        hostname_lower = hostname.lower()
        if hostname_lower.startswith('an'):
            return 'ALAN'
        elif hostname_lower.startswith('sv'):
            return 'SILVA'
        elif hostname_lower.startswith('av'):
            return 'ALVES'
        else:
            return 'Não Definido'

    def run(self):
        """Executa o ciclo completo de verificação e geração de relatórios."""
        print("Iniciando verificação de monitoramento do cluster HPC...")
        self._setup_output_files()
        if self.args['test_html']:
            self._generate_test_report()
            return
        all_results = self._run_all_checks()
        self._log_to_csv(all_results)
        print(f"Resultados registrados em: {self.config.CSV_LOG_FILE}")
        has_issues = any(c['status'] in [STATUS_WARN, STATUS_FAIL] for c in all_results)
        if has_issues or self.args['force_html']:
            if has_issues:
                print("Problemas detectados. Gerando relatório HTML...")
            else:
                print("Geração de relatório forçada. Gerando relatório HTML...")
            self._generate_html_report(all_results, self.scenario)
        else:
            print("Nenhum problema detectado. O relatório HTML não será gerado.")
        print("Verificação concluída.")

    def _run_all_checks(self) -> List[Dict[str, Any]]:
        """Instancia e executa todas as classes de verificação registradas."""
        checks = [
            CPUCheck(self.config), MemoryCheck(self.config), LoadAverageCheck(self.config),
            GPUCheck(self.config), ServicesCheck(self.config), DmesgCheck(self.config),
            NetworkErrorCheck(self.config), InfinibandCheck(self.config),
            BeeGFSDiskCheck(self.config), UptimeCheck(self.config)
        ]
        if self.args['smart_disks']:
            checks.append(DiskHealthCheck(self.config, self.args['smart_disks']))
        results = []
        for check in checks:
            try:
                res = check.execute()
                if res:
                    results.extend(res)
            except Exception as e:
                results.append({
                    'category': check.category, 'item': check.item,
                    'status': STATUS_FAIL, 'priority': PRIORITY_CRITICAL,
                    'details': f"Erro inesperado: {e}"
                })
        return results

    def _setup_output_files(self):
        """Cria o diretório de saída e o cabeçalho do arquivo CSV."""
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        if not os.path.exists(self.config.CSV_LOG_FILE):
            with open(self.config.CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['timestamp', 'category', 'item', 'status', 'priority', 'details'])

    def _log_to_csv(self, all_checks: List[Dict]):
        """Registra os resultados da verificação no arquivo CSV."""
        with open(self.config.CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            for c in all_checks:
                w.writerow([
                    self.timestamp, c.get('category','N/A'), c.get('item','N/A'),
                    c.get('status','N/A'), c.get('priority','N/A'), c.get('details','N/A')
                ])

    def _generate_html_report(self, all_checks: List[Dict], scenario: str):
        """Gera o relatório HTML final a partir dos resultados."""
        try:
            with open(self.config.TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                template = f.read()
        except FileNotFoundError:
            print(f"ERRO: Template '{self.config.TEMPLATE_FILE}' não encontrado.")
            return
        s_map = {
            STATUS_NORMAL: {'icon': '✅', 'class': 'status-normal'},
            STATUS_WARN:   {'icon': '⚠️', 'class': 'status-warn'},
            STATUS_FAIL:   {'icon': '❌', 'class': 'status-fail'}
        }
        p_map = {
            PRIORITY_CRITICAL: 'priority-critical', PRIORITY_HIGH: 'priority-high',
            PRIORITY_MEDIUM: 'priority-medium', PRIORITY_INFO: 'priority-info'
        }
        grouped, html = {}, ""
        for check in all_checks:
            grouped.setdefault(check['category'], []).append(check)
        for cat, items in sorted(grouped.items()):
            html += f'<div class="category"><h2>{cat}</h2>'
            for item in sorted(items, key=lambda x: x['item']):
                s_info = s_map.get(item['status'], {'icon': '?', 'class': ''})
                p, p_class = item.get('priority', PRIORITY_MEDIUM), p_map.get(item.get('priority', PRIORITY_MEDIUM), '')
                p_tag = f'<span class="priority-tag {p_class}">{p}</span>' if item['status'] != STATUS_NORMAL else ''
                sugg, sugg_html = get_kb_suggestion(item['details'], self.knowledge_base), ''
                if sugg:
                    sugg_html = f'<div class="item-suggestion"><strong>Sugestão:</strong> {sugg}</div>'
                html += (
                    f'<div class="item {s_info["class"]}">\n'
                    f'  {p_tag}\n'
                    f'  <div class="item-status">{s_info["icon"]}</div>\n'
                    f'  <div class="item-content">\n'
                    f'    <div class="item-title">{item["item"]} - <span>{item["status"]}</span></div>\n'
                    f'    <div class="item-details">{item["details"]}</div>{sugg_html}\n'
                    f'  </div>\n'
                    f'</div>'
                )
            html += '</div>'
        final_html = template.replace('{hostname}', self.hostname)
        final_html = final_html.replace('{timestamp}', self.timestamp)
        final_html = final_html.replace('{content}', html)
        final_html = final_html.replace('{scenario}', scenario)
        with open(self.config.HTML_REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write(final_html)
        print(f"Relatório HTML gerado em: {self.config.HTML_REPORT_FILE}")

    def _generate_test_report(self):
        """Gera um relatório de teste a partir do arquivo test_data.json."""
        print("Modo de teste: Gerando relatório HTML de exemplo...")
        test_data_path = os.path.join(self.config.SCRIPT_DIR, 'data', 'test_data.json')
        try:
            with open(test_data_path, 'r', encoding='utf-8') as f:
                test_data = json.load(f)
            self._generate_html_report(test_data, self.scenario)
            print("Relatório de teste gerado com sucesso.")
        except FileNotFoundError:
            print(f"ERRO: Arquivo de dados de teste não encontrado em '{test_data_path}'")
        except json.JSONDecodeError:
            print(f"ERRO: Falha ao decodificar o arquivo JSON de teste.")


def parse_cli_args() -> Dict[str, Any]:
    """Analisa os argumentos da linha de comando."""
    args = {
        'test_html': '--test-html' in sys.argv,
        'force_html': '--force-html' in sys.argv,
        'smart_disks': []
    }
    if '--smart-disks' in sys.argv:
        try:
            index = sys.argv.index('--smart-disks')
            if len(sys.argv) > index + 1 and not sys.argv[index + 1].startswith('--'):
                disks_str = sys.argv[index + 1]
                args['smart_disks'] = [d.strip() for d in disks_str.split(',') if d.strip()]
            else:
                print("AVISO: Argumento --smart-disks não foi seguido por uma lista de discos.")
        except IndexError:
            pass
    return args


def main():
    """Função principal que inicia o monitoramento."""
    cli_args = parse_cli_args()
    monitor = Monitor(args=cli_args)
    monitor.run()


if __name__ == '__main__':
    main()
