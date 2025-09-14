#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# name.........: monitor_hpc
# description..: Monitor HPC - Refactored Version (with os.popen)
# author.......: Alan da Silva Alves
# version......: 2.7.6
# date.........: 14/09/2025
# github.......: github.com/treinalinux

import os
import datetime
import csv
import sys
import time
import json
import re
from typing import List, Dict, Any, Tuple, Optional

STATUS_NORMAL, STATUS_WARN, STATUS_FAIL = 'NORMAL', 'ATENÇÃO', 'FALHA'
PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_INFO = 'P1 (Crítica)', 'P2 (Alta)', 'P3 (Média)', 'P4 (Informativa)'

class Config:
    CPU_THRESHOLD_WARN, MEM_THRESHOLD_WARN, LOAD_AVERAGE_RATIO_WARN = 85.0, 85.0, 1.5
    SSD_PERCENTAGE_USED_THRESHOLD_WARN, SSD_TEMPERATURE_THRESHOLD_WARN = 85.0, 70
    GPU_TEMP_THRESHOLD_WARN, GPU_UTIL_THRESHOLD_WARN, BEEGFS_USAGE_THRESHOLD_WARN = 85.0, 90.0, 90.0
    SERVICES_TO_CHECK = ['beegfs-client', 'grafana-server', 'mysql', 'mariadb', 'pacemaker', 'pcsd', 'cmdaemon', 'apache2']
    INTERFACES_TO_IGNORE = ['lo', 'virbr']
    PACEMAKER_MANAGED_SERVICES = ['mysql', 'mariadb', 'apache2', 'grafana-server']
    SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
    OUTPUT_DIR = os.path.join(os.getcwd(), 'report')
    CSV_LOG_FILE, HTML_REPORT_FILE = os.path.join(OUTPUT_DIR, 'hpc_monitoring_log.csv'), os.path.join(OUTPUT_DIR, 'hpc_status_report.html')
    KB_FILE, TEMPLATE_FILE = os.path.join(SCRIPT_DIR, 'data', 'knowledge_base.json'), os.path.join(SCRIPT_DIR, 'templates', 'report_template.html')
    HARDWARE_ERROR_KEYWORDS = ['error', 'fail', 'critical', 'fatal', 'segfault']

def run_command(command: str) -> Tuple[str, int]:
    pipe = os.popen(f'LC_ALL=C {command} 2>&1'); output = pipe.read().strip(); exit_status = pipe.close()
    code = 0
    if exit_status is not None:
        if os.WIFEXITED(exit_status): code = os.WEXITSTATUS(exit_status)
        else: code = 1
    return output, code

def format_bytes(size_kb: float) -> str:
    if size_kb == 0: return "0 KB"
    size_names = ("KB", "MB", "GB", "TB", "PB", "EB", "ZB")
    i, size = 0, float(size_kb)
    while size >= 1024 and i < len(size_names) - 1: size /= 1024.0; i += 1
    return f"{size:.1f} {size_names[i]}"

def load_knowledge_base(kb_file: str) -> Dict:
    if not os.path.exists(kb_file): return {}
    try:
        with open(kb_file, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, IOError): return {}

def get_kb_suggestion(details: str, knowledge_base: Dict) -> Optional[str]:
    for category in knowledge_base.values():
        for keyword, suggestion in category.items():
            if keyword.lower() in details.lower(): return suggestion
    return None

class BaseCheck:
    def __init__(self, config: Config): self.config, self.category, self.item = config, "N/A", "N/A"
    def execute(self) -> List[Dict[str, Any]]: raise NotImplementedError()
    def _build_result(self, status: str, priority: str, details: str, item: Optional[str] = None) -> Dict[str, Any]: return {'category': self.category, 'item': item or self.item, 'status': status, 'priority': priority, 'details': details}

class CPUCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Recursos de Sistema", "Uso de CPU"
    def _get_cpu_times(self) -> Optional[Tuple[int, int]]:
        try:
            with open('/proc/stat', 'r') as f: line = f.readline()
            parts, cpu_times = line.split(), [int(p) for p in line.split()[1:9]]
            return sum(cpu_times), cpu_times[3]
        except (IOError, IndexError, ValueError): return None
    def execute(self) -> List[Dict[str, Any]]:
        t1 = self._get_cpu_times()
        if not t1: return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, "Não foi possível ler /proc/stat.")]
        time.sleep(1)
        t2 = self._get_cpu_times()
        if not t2: return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, "Não foi possível ler /proc/stat na segunda amostragem.")]
        delta_total, delta_idle = t2[0] - t1[0], t2[1] - t1[1]
        usage = 100.0 * (delta_total - delta_idle) / delta_total if delta_total > 0 else 0.0
        s, p, d = (STATUS_WARN, PRIORITY_HIGH, f"Uso de {usage:.1f}% excede o limite.") if usage >= self.config.CPU_THRESHOLD_WARN else (STATUS_NORMAL, PRIORITY_INFO, f"Uso de {usage:.1f}%.")
        return [self._build_result(s, p, d)]

class MemoryCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Recursos de Sistema", "Uso de Memória"
    def execute(self) -> List[Dict[str, Any]]:
        try:
            mem_info = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(); 
                    if len(parts) >= 2: mem_info[parts[0].rstrip(':')] = int(parts[1])
            mem_total = mem_info['MemTotal']
            mem_used = mem_total - mem_info['MemFree'] - mem_info['Buffers'] - mem_info['Cached'] - mem_info.get('SReclaimable', 0)
            mem_usage = (mem_used / mem_total) * 100.0 if mem_total > 0 else 0.0
            s, p, d = (STATUS_WARN, PRIORITY_HIGH, f"Uso de {mem_usage:.1f}% excede o limite.") if mem_usage >= self.config.MEM_THRESHOLD_WARN else (STATUS_NORMAL, PRIORITY_INFO, f"Uso de {mem_usage:.1f}%.")
            return [self._build_result(s, p, d)]
        except (IOError, KeyError, ValueError) as e: return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, f"Não foi possível ler /proc/meminfo. Erro: {e}")]

class LoadAverageCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Recursos de Sistema", "Média de Carga"
    def execute(self) -> List[Dict[str, Any]]:
        try:
            with open('/proc/loadavg', 'r') as f: load_1m_str, load_5m_str, load_15m_str = f.read().split()[:3]
            load_1m = float(load_1m_str)
            nproc_out, nproc_code = run_command("nproc")
            num_cores = int(nproc_out) if nproc_code == 0 and nproc_out.isdigit() else 1
            load_ratio = load_1m / num_cores
            d = f"Carga (1m, 5m, 15m): {load_1m_str}, {load_5m_str}, {load_15m_str} ({num_cores} núcleos)."
            s, p = (STATUS_WARN, PRIORITY_HIGH) if load_ratio >= self.config.LOAD_AVERAGE_RATIO_WARN else (STATUS_NORMAL, PRIORITY_INFO)
            if s == STATUS_WARN: d += f" Carga de 1 minuto ({load_1m}) é alta para os núcleos."
            return [self._build_result(s, p, d)]
        except (IOError, ValueError) as e: return [self._build_result(STATUS_FAIL, PRIORITY_HIGH, f"Não foi possível ler /proc/loadavg. Erro: {e}")]

class GPUCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Recursos de GPU", "Status das GPUs"
    def execute(self) -> List[Dict[str, Any]]:
        _, code = run_command("nvidia-smi -L")
        if code != 0: return []
        query = "index,name,temperature.gpu,utilization.gpu,memory.used,memory.total"
        output, code = run_command(f"nvidia-smi --query-gpu={query} --format=csv,noheader,nounits")
        if code != 0: return [self._build_result(STATUS_FAIL, PRIORITY_HIGH, f"Falha ao executar nvidia-smi. Saída: {output}")]
        results = []
        for line in output.splitlines():
            try:
                idx, name, temp, util, mem_used, mem_total = [p.strip() for p in line.split(',')]
                temp, util, mem_used, mem_total = float(temp), float(util), float(mem_used), float(mem_total)
                mem_percent = (mem_used / mem_total) * 100 if mem_total > 0 else 0
                item_name = f'GPU {idx}: {name}'
                status, warnings = STATUS_NORMAL, []
                if temp >= self.config.GPU_TEMP_THRESHOLD_WARN: status, warnings = STATUS_WARN, warnings + [f"Temp: {temp}°C (limite: {self.config.GPU_TEMP_THRESHOLD_WARN}°C)"]
                if util >= self.config.GPU_UTIL_THRESHOLD_WARN: status, warnings = STATUS_WARN, warnings + [f"Uso: {util}% (limite: {self.config.GPU_UTIL_THRESHOLD_WARN}%)"]
                p, d = (PRIORITY_HIGH, ", ".join(warnings)) if status == STATUS_WARN else (PRIORITY_INFO, f"Temp: {temp}°C, Uso: {util}%, Memória: {mem_used:.0f}/{mem_total:.0f} MB ({mem_percent:.1f}%)")
                results.append(self._build_result(status, p, d, item=item_name))
            except (ValueError, IndexError): results.append(self._build_result(STATUS_FAIL, PRIORITY_HIGH, f'Falha ao analisar linha: "{line}"'))
        return results

class InfinibandCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Rede de Alta Performance", "Saúde do InfiniBand"
    def _check_error_counters(self, device_name: str, port_num: str) -> List[str]:
        counters, errors = ['symbol_error', 'link_error_recovery', 'link_downed', 'port_rcv_errors', 'port_xmit_discards'], []
        path_base = f"/sys/class/infiniband/{device_name}/ports/{port_num}/counters"
        if not os.path.isdir(path_base): return []
        for c_name in counters:
            try:
                with open(os.path.join(path_base, c_name), 'r') as f: value = int(f.read().strip())
                if value > 0: errors.append(f"{c_name.replace('_', ' ').title()}: {value}")
            except (IOError, ValueError): continue
        return errors
    def execute(self) -> List[Dict[str, Any]]:
        _, code = run_command("ibstat -V"); 
        if code != 0: return []
        ibstat_output, code = run_command("ibstat")
        if code != 0: return [self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, f"Falha ao executar 'ibstat'. Saída: {ibstat_output}")]
        results, local_ports_info, has_healthy_ib_port = [], {}, False
        for block in ibstat_output.split('CA \'')[1:]:
            lines, ca_name = block.splitlines(), block.splitlines()[0].split('\'')[0]
            ports, current_port = {}, None
            for line in lines[1:]:
                clean_line = line.strip()
                if clean_line.startswith('Port ') and clean_line.endswith(':'):
                    current_port = clean_line.split(':')[0]
                    if current_port not in ports: ports[current_port] = {}
                elif ':' in line and current_port:
                    key, value = line.split(':', 1); ports[current_port][key.strip()] = value.strip()
            for p_key, details in ports.items():
                port_guid = details.get('Port GUID', 'N/A')
                local_ports_info[port_guid] = {'ca_name': ca_name, 'port_key': p_key, 'details': details, 'connection': None}
                p_num = p_key.split()[-1]
                state, phys_state, link_layer, rate = details.get('State', 'N/A'), details.get('Physical state', 'N/A'), details.get('Link layer', 'N/A'), details.get('Rate', 'N/A')
                item = f"{ca_name} - {p_key}"
                if link_layer == 'InfiniBand':
                    if state == 'Active' and phys_state == 'LinkUp':
                        has_healthy_ib_port = True
                        errors = self._check_error_counters(ca_name, p_num)
                        if errors:
                            d = f"Link Ativo, mas com erros. Taxa: {rate}. Contadores: {', '.join(errors)}."
                            results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, d, item=item))
                    else:
                        d = f"Estado Lógico: {state} (Esperado: Active), Físico: {phys_state} (Esperado: LinkUp), Taxa: {rate}"
                        results.append(self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, d, item=item))
                elif link_layer == 'Ethernet' and (state != 'Active' or phys_state != 'LinkUp'):
                    d = f"Interface Ethernet sobre IB inativa. Estado: {state}, Físico: {phys_state}, Taxa: {rate}"
                    results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, d, item=item))
        if any(r['status'] == STATUS_FAIL for r in results): return results
        iblink_output, code = run_command("iblinkinfo")
        if code != 0: results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, "Não foi possível executar 'iblinkinfo' para verificar as conexões.")); return results
        for line in iblink_output.splitlines():
            for guid, port_info in local_ports_info.items():
                if guid in line and '==>' in line:
                    match = re.search(r'==>\s+(\d+)\s+(\d+)\[\s*\]\s+"([^"]+)"', line)
                    if match: port_info['connection'] = {'peer_lid': match.group(1), 'peer_port': match.group(2), 'peer_name': match.group(3).strip()}
                    break
        connection_details, all_ports_connected = [], True
        for guid, port_info in local_ports_info.items():
            details = port_info['details']
            if details.get('Link layer', 'N/A') != 'InfiniBand' or not (details.get('State') == 'Active' and details.get('Physical state') == 'LinkUp'): continue
            if port_info['connection']:
                lid, rate, peer_name, peer_port = details.get('Base lid', 'N/A'), details.get('Rate', 'N/A'), port_info['connection']['peer_name'].split('"')[0].strip(), port_info['connection']['peer_port']
                connection_details.append(f"  • {port_info['ca_name']}/{port_info['port_key'].split()[-1]} (LID: {lid}, Taxa: {rate}Gbps) -> {peer_name} (Porta: {peer_port})")
            else:
                all_ports_connected = False
                item = f"{port_info['ca_name']} - {port_info['port_key']}"
                results.append(self._build_result(STATUS_FAIL, PRIORITY_CRITICAL, "Porta ativa mas sem conexão detectada (verificado com iblinkinfo).", item=item))
        if has_healthy_ib_port and all_ports_connected and not any(r['status'] == STATUS_FAIL for r in results):
            details = "Todas as portas InfiniBand estão ativas, sem erros e conectadas:<br>" + "<br>".join(connection_details)
            results.insert(0, self._build_result(STATUS_NORMAL, PRIORITY_INFO, details, item="Resumo da Conexão InfiniBand"))
        return results

# ... (Restante do script completo)
class NetworkErrorCheck(BaseCheck):
    def __init__(self, config: Config): super().__init__(config); self.category, self.item = "Saúde da Rede", "Erros de Interface de Rede"
    def execute(self) -> List[Dict[str, Any]]:
        try:
            with open('/proc/net/dev', 'r') as f: lines = f.readlines()[2:]
        except IOError: return [self._build_result(STATUS_FAIL, PRIORITY_MEDIUM, "Não foi possível ler /proc/net/dev.")]
        results = []
        for line in lines:
            try:
                parts = line.split()
                interface = parts[0].strip(':')
                if any(interface.startswith(p) for p in self.config.INTERFACES_TO_IGNORE): continue
                rx_errs, rx_drop, tx_errs, tx_drop = int(parts[3]), int(parts[4]), int(parts[11]), int(parts[12])
                if (rx_errs + tx_errs) > 0 or (rx_drop + tx_drop) > 0:
                    d = f"Erros: {rx_errs + tx_errs} (RX:{rx_errs}, TX:{tx_errs}), Descartados: {rx_drop + tx_drop} (RX:{rx_drop}, TX:{tx_drop})"
                    results.append(self._build_result(STATUS_WARN, PRIORITY_MEDIUM, d, item=f'Interface {interface}'))
            except (ValueError, IndexError): continue
        if not results: results.append(self._build_result(STATUS_NORMAL, PRIORITY_INFO, "Nenhum erro ou pacote descartado encontrado."))
        return results

class DiskHealthCheck(BaseCheck):
    def __init__(self, config: Config, disks_to_check: List[str]):
        super().__init__(config); self.category, self.disks_to_check = "Saúde dos Discos (S.M.A.R.T.)", disks_to_check
    def execute(self) -> List[Dict[str, Any]]:
        _, code = run_command("smartctl -V")
        if code != 0: return [self._build_result(STATUS_FAIL, PRIORITY_MEDIUM, "A ferramenta 'smartctl' não foi encontrada.", item="Ferramenta smartctl")]
        results = []
        for disk_arg in self.disks_to_check:
            path, type_arg = disk_arg, ""
            if ':' in disk_arg: path, type_ = disk_arg.split(':', 1); type_arg = f"-d {type_}"
            item = f"Disco {path}"
            out, _ = run_command(f"smartctl -H {type_arg} {path}")
            s, p, d = STATUS_FAIL, PRIORITY_HIGH, f"Não foi possível determinar o estado S.M.A.R.T. Saída: {out}"
            if "PASSED" in out: s, p, d = STATUS_NORMAL, PRIORITY_INFO, "O teste de autoavaliação S.M.A.R.T. foi aprovado."
            elif "FAILED" in out: s, p, d = STATUS_FAIL, PRIORITY_CRITICAL, "O teste S.M.A.R.T. FALHOU. Recomenda-se a substituição do disco."
            elif "Disabled" in out: s, p, d = STATUS_WARN, PRIORITY_MEDIUM, "O suporte a S.M.A.R.T. está desativado."
            if s == STATUS_NORMAL:
                is_ssd, _ = run_command(f"cat /sys/block/{os.path.basename(path)}/queue/rotational")
                if is_ssd.strip() == '0':
                    warnings = self._check_ssd_attributes(path, type_arg)
                    if warnings: s, p, d = STATUS_WARN, PRIORITY_HIGH, d + " " + " ".join(warnings)
            results.append(self._build_result(s, p, d, item=item))
        return results
    def _check_ssd_attributes(self, path: str, type_arg: str) -> List[str]:
        out, _ = run_command(f"smartctl -A {type_arg} {path}")
        warnings = []
        for line in out.splitlines():
            try:
                if "Percentage Used" in line:
                    used = float(line.split()[-1])
                    if used >= self.config.SSD_PERCENTAGE_USED_THRESHOLD_WARN: warnings.append(f"Desgaste ({used}%) excede o limite.")
                elif "Temperature_Celsius" in line:
                    temp = int(line.split()[-1])
                    if temp >= self.config.SSD_TEMPERATURE_THRESHOLD_WARN: warnings.append(f"Temperatura ({temp}°C) excede o limite.")
            except (ValueError, IndexError): continue
        return warnings

class ServicesCheck(BaseCheck):
    def __init__(self, config: Config):
        super().__init__(config); self.category, self.item = "Serviços Essenciais", "Status dos Serviços"
    def execute(self) -> List[Dict[str, Any]]:
        results = []
        _, pacemaker_code = run_command("systemctl is-active pacemaker")
        is_pacemaker_active = (pacemaker_code == 0)
        if is_pacemaker_active:
            managed = ", ".join(self.config.PACEMAKER_MANAGED_SERVICES)
            d = f"Pacemaker ativo. Serviços ({managed}) são gerenciados pelo cluster e ignorados aqui."
            results.append(self._build_result(STATUS_NORMAL, PRIORITY_INFO, d, item="Gerenciamento via Pacemaker"))
        for service in self.config.SERVICES_TO_CHECK:
            if is_pacemaker_active and service in self.config.PACEMAKER_MANAGED_SERVICES: continue
            output, _ = run_command(f"systemctl status {service}")
            if "Loaded: not-found" in output or "could not be found" in output: continue
            item_name = f'Serviço: {service}'
            if "Active: active (running)" in output:
                s, p, d = STATUS_NORMAL, PRIORITY_INFO, f'O serviço {service} está ativo.'
            else:
                s, p = STATUS_FAIL, PRIORITY_CRITICAL
                d = f'O serviço {service} está inativo ou em falha.\nDetalhes:\n' + "\n".join(output.splitlines()[-5:])
            results.append(self._build_result(s, p, d, item=item_name))
        return results

class DmesgCheck(BaseCheck):
    def __init__(self, config: Config):
        super().__init__(config); self.category, self.item = "Hardware e S.O.", "Logs do Kernel (dmesg)"
    def execute(self) -> List[Dict[str, Any]]:
        keys = '|'.join(self.config.HARDWARE_ERROR_KEYWORDS)
        out, code = run_command(f"dmesg | grep -iE '({keys})'")
        if code == 0 and out: s, p, d = STATUS_WARN, PRIORITY_HIGH, f"Possíveis erros de hardware encontrados:\n{out}"
        elif "Operation not permitted" in out: s, p, d = STATUS_WARN, PRIORITY_MEDIUM, "Não foi possível ler logs do kernel. Execute com 'sudo'."
        else: s, p, d = STATUS_NORMAL, PRIORITY_INFO, "Nenhum erro crítico recente encontrado."
        return [self._build_result(s, p, d)]

class BeeGFSDiskCheck(BaseCheck):
    def __init__(self, config: Config):
        super().__init__(config); self.category, self.item = "Uso de Disco BeeGFS", "Uso das Partições"
    def _find_beegfs_mounts(self) -> List[str]:
        mounts = []
        output, code = run_command("mount")
        if code != 0: return mounts
        for line in output.splitlines():
            if ' on /BeeGFS' in line:
                try:
                    mount_point = line.split(' on ')[1].split(' ')[0]
                    if mount_point.startswith('/BeeGFS'): mounts.append(mount_point)
                except IndexError: continue
        return sorted(list(set(mounts)))
    def execute(self) -> List[Dict[str, Any]]:
        beegfs_mounts = self._find_beegfs_mounts()
        if not beegfs_mounts: return []
        results, total_size_kb, total_used_kb = [], 0, 0
        for mount in beegfs_mounts:
            output, code = run_command(f"df -k {mount}")
            if code != 0 or len(output.splitlines()) < 2: continue
            try:
                parts = output.splitlines()[1].split()
                size_kb, used_kb, avail_kb, use_percent = int(parts[1]), int(parts[2]), int(parts[3]), float(parts[4].replace('%', ''))
                total_size_kb += size_kb; total_used_kb += used_kb
                status, priority = (STATUS_WARN, PRIORITY_HIGH) if use_percent >= self.config.BEEGFS_USAGE_THRESHOLD_WARN else (STATUS_NORMAL, PRIORITY_INFO)
                details = f"Uso: {use_percent:.1f}%. Total: {format_bytes(size_kb)}, Usado: {format_bytes(used_kb)}, Disponível: {format_bytes(avail_kb)}."
                results.append(self._build_result(status, priority, details, item=f'Uso da Partição {mount}'))
            except (ValueError, IndexError): continue
        if total_size_kb > 0:
            agg_usage, agg_avail = (total_used_kb / total_size_kb) * 100.0, total_size_kb - total_used_kb
            status, priority = (STATUS_WARN, PRIORITY_HIGH) if agg_usage >= self.config.BEEGFS_USAGE_THRESHOLD_WARN else (STATUS_NORMAL, PRIORITY_INFO)
            details = f"Uso total: {agg_usage:.1f}%. Total: {format_bytes(total_size_kb)}, Usado: {format_bytes(total_used_kb)}, Disponível: {format_bytes(agg_avail)}."
            results.append(self._build_result(status, priority, details, item='Uso Agregado das Partições'))
        return results

class Monitor:
    def __init__(self, args: Dict[str, Any]):
        self.args, self.config = args, Config()
        self.knowledge_base = load_knowledge_base(self.config.KB_FILE)
        self.hostname, _ = run_command("hostname")
        self.timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    def run(self):
        print("Iniciando verificação de monitoramento do cluster HPC...")
        self._setup_output_files()
        if self.args['test_html']: self._generate_test_report(); return
        all_results = self._run_all_checks()
        self._log_to_csv(all_results)
        print(f"Resultados registrados em: {self.config.CSV_LOG_FILE}")
        has_issues = any(c['status'] in [STATUS_WARN, STATUS_FAIL] for c in all_results)
        if has_issues or self.args['force_html']:
            if has_issues: print("Problemas detectados. Gerando relatório HTML...")
            else: print("Geração de relatório forçada. Gerando relatório HTML...")
            self._generate_html_report(all_results)
        else:
            print("Nenhum problema detectado. O relatório HTML não será gerado.")
        print("Verificação concluída.")
    def _run_all_checks(self) -> List[Dict[str, Any]]:
        checks = [
            CPUCheck(self.config), MemoryCheck(self.config), LoadAverageCheck(self.config),
            GPUCheck(self.config), ServicesCheck(self.config), DmesgCheck(self.config),
            NetworkErrorCheck(self.config), InfinibandCheck(self.config),
            BeeGFSDiskCheck(self.config)
        ]
        if self.args['smart_disks']:
            checks.append(DiskHealthCheck(self.config, self.args['smart_disks']))
        results = []
        for check in checks:
            try:
                res = check.execute()
                if res: results.extend(res)
            except Exception as e:
                results.append({'category': check.category, 'item': check.item, 'status': STATUS_FAIL, 
                                    'priority': PRIORITY_CRITICAL, 'details': f"Erro inesperado: {e}"})
        return results
    def _setup_output_files(self):
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        if not os.path.exists(self.config.CSV_LOG_FILE):
            with open(self.config.CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f); w.writerow(['timestamp', 'category', 'item', 'status', 'priority', 'details'])
    def _log_to_csv(self, all_checks: List[Dict]):
        with open(self.config.CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            for c in all_checks:
                w.writerow([self.timestamp, c.get('category','N/A'), c.get('item','N/A'), c.get('status','N/A'), c.get('priority','N/A'), c.get('details','N/A')])
    def _generate_html_report(self, all_checks: List[Dict]):
        try:
            with open(self.config.TEMPLATE_FILE, 'r', encoding='utf-8') as f: template = f.read()
        except FileNotFoundError: print(f"ERRO: Template '{self.config.TEMPLATE_FILE}' não encontrado."); return
        s_map = {STATUS_NORMAL: {'icon': '✅', 'color': '#28a745'}, STATUS_WARN: {'icon': '⚠️', 'color': '#ffc107'}, STATUS_FAIL: {'icon': '❌', 'color': '#dc3545'}}
        p_map = {PRIORITY_CRITICAL: {'color': '#721c24', 'bg_color': '#f8d7da'}, PRIORITY_HIGH: {'color': '#856404', 'bg_color': '#fff3cd'},
                 PRIORITY_MEDIUM: {'color': '#004085', 'bg_color': '#cce5ff'}, PRIORITY_INFO: {'color': '#155724', 'bg_color': '#d4edda'}}
        grouped, html = {}, ""
        for check in all_checks: grouped.setdefault(check['category'], []).append(check)
        for cat, items in sorted(grouped.items()):
            html += f'<div class="category"><h2>{cat}</h2>'
            for item in sorted(items, key=lambda x: x['item']):
                s_info = s_map.get(item['status'], {'icon': '?', 'color': '#6c757d'})
                p, p_info, p_tag = item.get('priority', PRIORITY_MEDIUM), p_map.get(item.get('priority', PRIORITY_MEDIUM)), ''
                if item['status'] != STATUS_NORMAL and p_info:
                    p_tag = (f'<span class="priority-tag" style="--p-color: {p_info.get("color", "#6c757d")}; '
                             f'--p-bg-color: {p_info.get("bg_color", "#e9ecef")};">{p}</span>')
                sugg, sugg_html = get_kb_suggestion(item['details'], self.knowledge_base), ''
                if sugg: sugg_html = f'<div class="item-suggestion"><strong>Sugestão:</strong> {sugg}</div>'
                html += (f'<div class="item" style="border-left: 5px solid {s_info["color"]};"><div class="item-status">{s_info["icon"]}</div>'
                         f'<div class="item-content"><div class="item-title">{item["item"]} - <span style="color: {s_info["color"]}; '
                         f'margin-left: 4px;">{item["status"]}</span>{p_tag}</div><div class="item-details">{item["details"]}</div>{sugg_html}</div></div>')
            html += '</div>'
        final_html = template.replace('{hostname}', self.hostname).replace('{timestamp}', self.timestamp).replace('{content}', html)
        with open(self.config.HTML_REPORT_FILE, 'w', encoding='utf-8') as f: f.write(final_html)
        print(f"Relatório HTML gerado em: {self.config.HTML_REPORT_FILE}")
    def _generate_test_report(self):
        print("Modo de teste: Gerando relatório HTML de exemplo a partir de arquivo JSON...")
        test_data_path = os.path.join(self.config.SCRIPT_DIR, 'data', 'test_data.json')
        try:
            with open(test_data_path, 'r', encoding='utf-8') as f: test_data = json.load(f)
            self._generate_html_report(test_data)
            print("Relatório de teste gerado com sucesso.")
        except FileNotFoundError: print(f"ERRO: Arquivo de dados de teste não encontrado em '{test_data_path}'")
        except json.JSONDecodeError: print(f"ERRO: Falha ao decodificar o arquivo JSON de teste em '{test_data_path}'")

def parse_cli_args() -> Dict[str, Any]:
    args = {'test_html': '--test-html' in sys.argv, 'force_html': '--force-html' in sys.argv, 'smart_disks': []}
    if '--smart-disks' in sys.argv:
        try:
            index = sys.argv.index('--smart-disks')
            if len(sys.argv) > index + 1 and not sys.argv[index + 1].startswith('--'):
                disks_str = sys.argv[index + 1]
                args['smart_disks'] = [d.strip() for d in disks_str.split(',') if d.strip()]
            else:
                print("AVISO: Argumento --smart-disks não foi seguido por uma lista de discos.")
        except IndexError: pass
    return args

def main():
    cli_args = parse_cli_args()
    monitor = Monitor(args=cli_args)
    monitor.run()

if __name__ == '__main__':
    main()
