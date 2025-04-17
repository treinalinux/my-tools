#!/usr/bin/env python3

# Name.......: Cpu Monitor Check
# Version....: 0.1.2
# Description: Monitor overload of cpu 
# Create by..: Alan da Silva ALves
# Created at.: 04/17/2025

import os
import time
from typing import List, Tuple
# import select
# import errno


def get_cpu_count() -> int:
    """
    Returns the number of logical CPUs in the system using /proc/cpuinfo.
    """
    count = 0
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('processor'):
                    count += 1
    except FileNotFoundError:
        print("Error: /proc/cpuinfo not found. Cannot determine CPU count.")
        return 1  # Return a default value to avoid errors later
    return count


def get_cpu_usage_percent() -> List[float]:
    """
    Returns the CPU usage percentage for each CPU core by reading /proc/stat.

    Returns:
        A list of floats representing the CPU usage percentage for each core.
    """
    cpu_usages_before: List[tuple[int, ...]] = []
    cpu_usages_after: List[tuple[int, ...]] = []

    try:
        with open('/proc/stat', 'r') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('cpu'):
                    parts = line.split()
                    if len(parts) < 8:  # Skip the 'cpu' line
                        continue
                    user = int(parts[1])
                    nice = int(parts[2])
                    system = int(parts[3])
                    idle = int(parts[4])
                    iowait = int(parts[5])
                    irq = int(parts[6])
                    softirq = int(parts[7])
                    total = user + nice + system + idle + iowait + irq + softirq
                    cpu_usages_before.append((user, nice, system, idle, total))

        time.sleep(0.1)  # Short delay to calculate usage over time

        with open('/proc/stat', 'r') as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith('cpu'):
                    parts = line.split()
                    if len(parts) < 8:
                        continue
                    user = int(parts[1])
                    nice = int(parts[2])
                    system = int(parts[3])
                    idle = int(parts[4])
                    iowait = int(parts[5])
                    irq = int(parts[6])
                    softirq = int(parts[7])
                    total = user + nice + system + idle + iowait + irq + softirq
                    cpu_usages_after.append((user, nice, system, idle, total))

    except FileNotFoundError:
        print("Error: /proc/stat not found. Cannot calculate CPU usage.")
        return [0.0] * get_cpu_count()  # Return a list of zeros

    percentages: List[float] = []
    for i in range(len(cpu_usages_before)):
        prev_user, prev_nice, prev_system, prev_idle, prev_total = cpu_usages_before[i]
        curr_user, curr_nice, curr_system, curr_idle, curr_total = cpu_usages_after[i]

        delta_idle = curr_idle - prev_idle
        delta_total = curr_total - prev_total

        cpu_percentage = (delta_total - delta_idle) / delta_total * 100.0 if delta_total else 0.0
        percentages.append(cpu_percentage)

    return percentages[1:]  # Exclude overall CPU usage


#def is_server_overloaded(cpu_percentages: List[float], threshold: float = 80.0) -> bool:
def is_server_overloaded(cpu_percentages: List[float], threshold: float = 10.0) -> bool:
    """
    Checks if the server is overloaded based on average CPU usage.

    Args:
        cpu_percentages: A list of CPU usage percentages for each core.
        threshold: The average CPU usage percentage threshold (default: 80.0).

    Returns:
        True if the average CPU usage exceeds the threshold, False otherwise.
    """
    total_usage = sum(cpu_percentages) / len(cpu_percentages) if cpu_percentages else 0.0
    return total_usage > threshold


def get_top_cpu_consuming_processes(top_n: int = 10) -> List[Tuple[str, float]]:
    """
    Returns the top N processes consuming the most CPU using os.popen.

    Args:
        top_n: The number of top processes to return (default: 10).

    Returns:
        A list of tuples, where each tuple contains (process_name, cpu_percent).
    """
    processes: List[Tuple[str, float]] = []
    try:
        ps_command = "ps -eo pid,%cpu,comm --sort=-%cpu | head -n {}".format(top_n + 1)
        with os.popen(ps_command) as proc:
            output = proc.read()
        lines = output.strip().split('\n')[1:]  # Skip header

        for line in lines:
            parts = line.split(None, 2)  # Split into PID, %CPU, and command
            if len(parts) < 3:
                continue  # Skip incomplete lines
            try:
                cpu_percent = float(parts[1].strip())
                process_name = parts[2].strip()
                processes.append((process_name, cpu_percent))
            except ValueError:
                continue  # Skip lines with invalid CPU values

    except OSError as e:
        print(f"Error executing ps command: {e}")

    return processes


def cpu_monitor(value: int = 60, control: bool = True):
    cpu_count = get_cpu_count()
    print(f"Number of CPUs: {cpu_count}")

    countdown = value

    try:
        while countdown >= 0:
            cpu_usage = get_cpu_usage_percent()
            for i, usage in enumerate(cpu_usage):
                print(f"CPU {i}: {usage:.2f}%")

            if is_server_overloaded(cpu_usage):
                print("WARNING: Server is experiencing high CPU load!")
                top_processes = get_top_cpu_consuming_processes()
                if top_processes:
                    print("Top CPU-consuming processes:")
                    for process, usage in top_processes:
                        print(f"  {process}: {usage:.2f}%")

                if control:
                    countdown = 0
            else:
                print("CPU load is within acceptable limits.")

            time.sleep(1)
            print("-" * 20)
            print(f"Countdown: {countdown}s")
            countdown -= 1
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    cpu_monitor(120, False)
