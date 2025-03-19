#!/usr/bin/env python3

import os
import time
import datetime
import random


HIGH_CPU_LOAD_THRESHOLD = 70  # Limite para carga alta (em porcentagem)
HIGH_LOAD_CPU_PERCENTAGE = 0.50  # 10% das CPUs com carga alta
MONITORING_TIME = 60


def read_cpu_stats():
    """Lê as estatísticas da CPU do arquivo /proc/stat."""
    try:
        with open("/proc/stat", "r") as f:
            lines = f.readlines()
        return lines
    except FileNotFoundError:
        print("Arquivo /proc/stat não encontrado.")
        return None
    except Exception as e:
        print(f"Erro ao ler estatísticas da CPU: {e}")
        return None


def process_cpu_stats(lines):
    """Processa as estatísticas da CPU e retorna um dicionário."""
    cpu_stats = {}
    for line in lines:
        if line.startswith("cpu"):
            parts = line.split()
            if parts[0] == "cpu":
                continue
            cpu_name = parts[0]
            values = list(map(int, parts[1:]))
            cpu_stats[cpu_name] = {
                "user": values[0], "nice": values[1], "system": values[2], "idle": values[3],
                "iowait": values[4], "irq": values[5], "softirq": values[6], "steal": values[7],
                "guest": values[8], "guest_nice": values[9],
            }
    return cpu_stats


def calculate_cpu_usage(previous_cpu_stats, current_cpu_stats):
    """Calculates the utilization of each CPU."""
    cpu_usage = {}
    for cpu_name in previous_cpu_stats:
        old_stats = previous_cpu_stats[cpu_name]
        new_stats = current_cpu_stats[cpu_name]

        delta_total = sum(new_stats.values()) - sum(old_stats.values())
        delta_idle = new_stats["idle"] - old_stats["idle"]

        if delta_total == 0:
            cpu_usage[cpu_name] = 0.0
            continue

        cpu_usage[cpu_name] = 100 * (delta_total - delta_idle) / delta_total
    return cpu_usage


def check_high_cpu_load(cpu_usage):
    """Verifica e imprime quais CPUs estão com carga alta."""
    high_load_cpus = []
    for cpu_name, usage in cpu_usage.items():
        if usage > HIGH_CPU_LOAD_THRESHOLD:
            high_load_cpus.append((cpu_name, usage))

    total_cpus = len(cpu_usage)
    if len(high_load_cpus) >= total_cpus * HIGH_LOAD_CPU_PERCENTAGE:
        cpu_high = HIGH_LOAD_CPU_PERCENTAGE * 100
        print(f"Mais de {cpu_high}% das CPUs com carga alta:")
        for cpu_name, usage in high_load_cpus:
            print(f"  {cpu_name}: {usage:.2f}%")

    if high_load_cpus:
        print("\nCPUs com altas cargas:")
        for cpu_name, usage in high_load_cpus:
            print(f"  {cpu_name}: {usage:.2f}%")
        identify_highest_cpu_process()


def identify_high_cpu_processes():
    """Identifica processos consumindo mais CPU."""
    try:
        output = os.popen('ps -eo %cpu,pid,command').read()
        lines = output.splitlines()[1:]
        processes = []
        for line in lines:
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                cpu_percent, pid, command = parts
                try:
                    cpu_percent = float(cpu_percent)
                    pid = int(pid)
                    processes.append((cpu_percent, pid, command))
                except ValueError:
                    pass

        processes.sort(reverse=True)

        print("\nProcessos com maior consumo de CPU:")
        for cpu_percent, pid, command in processes[:5]:
            print(f"  {cpu_percent:.2f}%  PID: {pid}  {command}")

    except Exception as e:
        print(f"Erro ao identificar processos: {e}")


def identify_highest_cpu_process():
    """Identifica o processo com maior consumo de CPU."""
    try:
        output = os.popen('ps -eo %cpu,pid,command').read()
        lines = output.splitlines()[1:]
        processes = []
        for line in lines:
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                cpu_percent, pid, command = parts
                try:
                    cpu_percent = float(cpu_percent)
                    pid = int(pid)
                    processes.append((cpu_percent, pid, command))
                except ValueError:
                    pass

        if processes:
          highest_process = max(processes) # Encontra o processo com maior consumo
          print("\nProcesso com maior consumo de CPU:")
          print(f"  {highest_process[0]:.2f}%  PID: {highest_process[1]}  {highest_process[2]}")
        else:
            print("\nNenhum processo em execução encontrado.")

    except Exception as e:
        print(f"Erro ao identificar processos: {e}")


def monitor_cpu_usage():
    """Monitora o uso da CPU continuamente."""
    previous_cpu_stats = None
    start_time = time.time()

    while time.time() - start_time < MONITORING_TIME:
        lines = read_cpu_stats()
        if lines:
            current_cpu_stats = process_cpu_stats(lines)
            if previous_cpu_stats:
                cpu_usage = calculate_cpu_usage(previous_cpu_stats, current_cpu_stats)
                check_high_cpu_load(cpu_usage)
            previous_cpu_stats = current_cpu_stats
        time.sleep(1)


def compliance_report():
    """
    Imprime um relatório de conformidade em horários aleatórios entre 6h e 6h59 ou 18h e 18h59.
    """
    now = datetime.datetime.now()
    current_hour = now.hour

    if current_hour == 6:
        random_minute = random.randint(0, 59)
        target_time = now.replace(minute=random_minute, second=0, microsecond=0)
        remaining_time = (target_time - now).total_seconds()
        if remaining_time > 0:
            time.sleep(remaining_time)
            print(f"Relatório de conformidade realizado às {datetime.datetime.now().strftime('%H:%M:%S')}")
    elif current_hour == 18:
        random_minute = random.randint(0, 59)
        target_time = now.replace(minute=random_minute, second=0, microsecond=0)
        remaining_time = (target_time - now).total_seconds()
        if remaining_time > 0:
            time.sleep(remaining_time)
            print(f"Relatório de conformidade realizado às {datetime.datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    monitor_cpu_usage()
