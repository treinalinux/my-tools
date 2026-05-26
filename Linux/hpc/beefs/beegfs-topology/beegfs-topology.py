#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name.........: Topologia BeeGFS
# description..: Ferramenta que checa a topologia usada na criação do centário.
# author.......: Alan da Silva Alves
# version......: 0.0.1
# date.........: 5/26/2026
# depends......: ethtool
# github.......: github.com/treinalinux
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os
import socket
import re
import argparse

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def run_cmd(cmd):
    """Executa comando no shell via os.popen de forma protegida e captura a saída."""
    try:
        # Garante a supressão de erros no shell (stderr para dev/null) se não existir no comando
        safe_cmd = cmd if "2>" in cmd else f"{cmd} 2>/dev/null"
        
        # O bloco 'with' garante o fechamento seguro do descritor (pipe) após a leitura
        with os.popen(safe_cmd) as proc:
            output = proc.read()
            
        return output.strip()
    except Exception:
        # Em caso de pânico no SO ou falha de alocação de memória do pipe, retorna vazio
        return ""


def get_beegfs_network():
    """Analisa o check-servers para extrair IP, Porta e Protocolo apenas se estiver REACHABLE."""
    out = run_cmd("beegfs-check-servers")
    net_info = {}
    current_host = None
    is_reachable = False
    
    for line in out.splitlines():
        match_base = re.search(r'^(\S+)\s+\[ID:\s*\d+\]:(.*)', line.strip())
        if match_base:
            current_host = match_base.group(1)
            status_str = match_base.group(2).lower()
            
            if "unreachable" in status_str:
                is_reachable = False
                continue
            else:
                is_reachable = True
            
            match_inline = re.search(r'reachable at (\S+):(\d+) \(protocol: (\w+)\)', line)
            if match_inline and is_reachable:
                net_info[current_host] = {
                    'ip': match_inline.group(1), 
                    'port': match_inline.group(2), 
                    'proto': match_inline.group(3)
                }
                current_host = None
            continue
            
        if current_host and is_reachable:
            match_route = re.search(r'Route: (\S+):(\d+) \(protocol: (\w+)\)', line)
            if match_route:
                if current_host not in net_info:
                    net_info[current_host] = {
                        'ip': match_route.group(1), 
                        'port': match_route.group(2), 
                        'proto': match_route.group(3)
                    }
                current_host = None
                
    return net_info


def probe_os_details(hostname, ip, proto):
    """Sondagem profunda via SSH para Hardware de Storage, Multipath, iSCSI Targets e Rede."""
    if not ip:
        return {"link": "[ Sem IP ]", "backend": "[ Sem IP ]"}
        
    ssh_cmd = (
        f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@{ip} '"
        "mpaths=$(lsblk -d -o TYPE 2>/dev/null | grep -iE \"mpath|multipath\" -c); "
        "hw=$(lsblk -d -n -o VENDOR,MODEL,TRAN 2>/dev/null | grep -vE \"loop|ram|cdrom\" | awk \"{\\$1=\\$1;print}\" | sort -u | paste -sd \", \"); "
        "paths=$(lsblk -d -n -o TYPE 2>/dev/null | grep -vE \"loop|ram|cdrom\" | wc -l); "
        "iscsi=$(iscsiadm -m session 2>/dev/null | awk \"{print \\$3}\" | cut -d, -f1 | sort -u | paste -sd \", \"); "
        f"iface=$(ip route get {ip} 2>/dev/null | awk \"{{for(i=1;i<=NF;i++) if(\\$i==\\\"dev\\\") print \\$(i+1)}}\" | head -n1); "
        "speed=$(cat /sys/class/net/$iface/speed 2>/dev/null); "
        "echo \"MPATH:$mpaths|HW:$hw|PATHS:$paths|SPEED:$speed|ISCSI:$iscsi\"'"
    )
    out = run_cmd(ssh_cmd)
    
    if not out:
        return {"link": "[ Timeout/Recusado ]", "backend": "[ Timeout/Recusado ]"}
    
    match_mpath = re.search(r'MPATH:(\d+)', out)
    match_hw = re.search(r'HW:(.*?)\|PATHS', out)
    match_paths = re.search(r'PATHS:(\d+)', out)
    match_speed = re.search(r'SPEED:(-?\d+)', out)
    match_iscsi = re.search(r'ISCSI:(.*)', out)
    
    mpath_count = int(match_mpath.group(1)) if match_mpath else 0
    hw_str = match_hw.group(1).strip() if match_hw and match_hw.group(1).strip() else "Virtual/Desconhecido"
    paths_count = int(match_paths.group(1)) if match_paths else 1
    speed = int(match_speed.group(1)) if match_speed and match_speed.group(1) else 0
    iscsi_str = match_iscsi.group(1).strip() if match_iscsi and match_iscsi.group(1).strip() else ""
    
    target_info = f" (Targets: {iscsi_str})" if iscsi_str else ""
    
    if mpath_count > 0:
        backend_str = f"SAN Multipath (MPIO Ativo) -> {hw_str} [{paths_count} caminhos]{target_info}"
    elif "iscsi" in hw_str.lower() or "fc" in hw_str.lower():
        backend_str = f"Block Storage Remoto -> {hw_str} [{paths_count} conexões]{target_info}"
    else:
        backend_str = f"Storage Local/Direct -> {hw_str} [{paths_count} disco(s)]"
        
    if proto.upper() == "RDMA":
        speed_str = f"{int(speed/1000)} Gbps (InfiniBand/RoCE)" if speed > 0 else "RDMA Ativo"
    elif speed >= 10000:
        speed_str = f"{int(speed/1000)} Gbps (TCP Alta Velocidade)"
    elif speed > 0:
        speed_str = f"{speed} Mbps"
    else:
        speed_str = "Velocidade Virtual/Desconhecida"
        
    return {"link": speed_str, "backend": backend_str}


def is_pacemaker_active(ip):
    if not ip: return False
    ssh_cmd = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=2 root@{ip} 'systemctl is-active pacemaker corosync'"
    out = run_cmd(ssh_cmd)
    return "active" in out.lower()


def get_pacemaker_deep_details(ip, raw_resources):
    """Interroga as configurações internas do Pacemaker para extrair caminhos de disco, mounts e VIPs reais."""
    data = {'nodes': 'Desconhecido', 'vip_details': 'Não encontrado', 'storage_area': 'Não encontrada', 'resources': []}
    
    ssh_nodes = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=2 root@{ip} 'pcs status nodes | grep -i online'"
    nodes_out = run_cmd(ssh_nodes)
    if nodes_out: data['nodes'] = nodes_out.strip()

    vip_res = None
    for res_line in raw_resources:
        if "ipaddr2" in res_line.lower():
            match = re.search(r'([\w_-]+)\s+\(ocf::heartbeat:IPaddr2\)', res_line)
            if match: vip_res = match.group(1)

    if vip_res:
        ssh_vip = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=2 root@{ip} 'pcs resource config {vip_res} | grep -i ip='"
        vip_out = run_cmd(ssh_vip)
        if vip_out:
            ip_m = re.search(r'ip=["\']?([^"\']+)["\']?', vip_out)
            data['vip_details'] = f"VIP [{ip_m.group(1)}] associado ao recurso {vip_res}" if ip_m else vip_out

    ssh_fs = f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=2 root@{ip} 'pcs resource config | grep -E \"device=|directory=\"'"
    fs_out = run_cmd(ssh_fs)
    if fs_out:
        dev_m = re.search(r'device=["\']?([^"\'\s]+)["\']?', fs_out)
        dir_m = re.search(r'directory=["\']?([^"\'\s]+)["\']?', fs_out)
        
        dev_str = dev_m.group(1) if dev_m else "?"
        dir_str = dir_m.group(1) if dir_m else "?"
        
        if dev_str != "?" or dir_str != "?":
            data['storage_area'] = f"Device: {dev_str} ➔ Montado em: {dir_str}"

    return data


def get_pacemaker_status(ip):
    ssh_cmd = (
        f"ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=3 root@{ip} '"
        "echo \"---RES---\"; "
        "pcs resource status; "
        "echo \"---ORD---\"; "
        "pcs constraint order'"
    )
    out = run_cmd(ssh_cmd)
    if not out: return None
    
    data = {'resources': [], 'orders': []}
    section = 'base'
    for line in out.splitlines():
        line = line.strip()
        if not line or 'Ordering Constraints:' in line or 'Daemon Status:' in line: continue
        if line == '---RES---': section = 'resources'
        elif line == '---ORD---': section = 'orders'
        else:
            clean_line = re.sub(r'\s+', ' ', line)
            if section == 'resources': data['resources'].append(clean_line)
            elif section == 'orders': data['orders'].append(clean_line)
    return data


def get_capacities():
    out = run_cmd("beegfs-df -e")
    caps = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit():
            tid, status = parts[0], parts[1]
            if status.lower() == "online" and len(parts) >= 6:
                caps[tid] = {"status": "ONLINE", "total": parts[4], "free": parts[5]}
            else:
                caps[tid] = {"status": status.upper(), "total": "N/A", "free": "N/A"}
    return caps


def get_nodes(nodetype):
    out = run_cmd(f"beegfs-ctl --listnodes --nodetype={nodetype}")
    nodes = {}
    for line in out.splitlines():
        match = re.search(r'^(\S+)\s+\[ID:\s*(\d+)\]', line.strip())
        if match: nodes[match.group(2)] = match.group(1)
    return nodes


def get_targets(nodetype):
    out = run_cmd(f"beegfs-ctl --listtargets --nodetype={nodetype}")
    targets = {}
    for line in out.splitlines():
        if "TargetID" in line or "===" in line: continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[-1].isdigit():
            targets[parts[0]] = parts[-1]
    return targets


def get_mirrors(nodetype):
    out = run_cmd(f"beegfs-ctl --listmirrorgroups --nodetype={nodetype}")
    mirrors = []
    for line in out.splitlines():
        if "BuddyGroupID" in line or "===" in line: continue
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit():
            mirrors.append((parts[0], parts[1], parts[2]))
    return mirrors


def print_node_details(hostname, node_id, target_id, capacities, networks, is_ha=False):
    cap = capacities.get(target_id, {"status": "UNKNOWN", "total": "?", "free": "?"})
    net = networks.get(hostname, {})
    
    if net:
        os_info = probe_os_details(hostname, net['ip'], net['proto']) if cap["status"] == "ONLINE" else {"link": "[ Offline ]", "backend": "[ Offline ]"}
        net_str = f"{net['ip']}:{net['port']} | BeeGFS Proto: {net['proto'].upper()}"
    else:
        os_info = {"link": "[ Unreachable ]", "backend": "[ Unreachable ]"}
        net_str = "Desconhecido / Unreachable"
        
    print(f"    ├─ [ {hostname} ] (Node: {node_id} | Target: {target_id})")
    print(f"    │    ├─ Rede App:   {net_str}")
    print(f"    │    ├─ Storage:    {cap['status']} | {cap['free']} livre de {cap['total']}")
    print(f"    │    ├─ Hardware:   {os_info['backend']}")
    print(f"    │    ├─ Rede OS:    {os_info['link']}")
    
    if is_ha and net:
        pm_status = get_pacemaker_status(net['ip'])
        if pm_status:
            pm_deep = get_pacemaker_deep_details(net['ip'], pm_status['resources'])
            print(f"    │    └─ [ Integração Pacemaker HA ]")
            print(f"    │         ├─ Nós Físicos:   {pm_deep['nodes']}")
            print(f"    │         ├─ Interface VIP: {pm_deep['vip_details']}")
            print(f"    │         ├─ Área Ofertada: {pm_deep['storage_area']}")
            print(f"    │         ├─ Recursos Ativos SO:")
            for r in pm_status['resources']:
                print(f"    │         │    ├─ {r}")
            if pm_status['orders']:
                print(f"    │         └─ Restrições de Ordem do Cluster:")
                for idx, o in enumerate(pm_status['orders']):
                    prefix = "└─" if idx == len(pm_status['orders']) - 1 else "├─"
                    print(f"    │              {prefix} {o}")
            else:
                print(f"    │         └─ Restrições de Ordem: Nenhuma configurada")


def draw_tier(tier_name, nodetype, capacities, networks):
    print(f"\n[{tier_name} TIER]")
    print("=" * 80)
    
    nodes = get_nodes(nodetype)
    targets = get_targets(nodetype)
    mirrors = get_mirrors(nodetype)
    
    if not nodes:
        print("  [!] Nenhum nó detectado.")
        return

    mirrored_targets = set()
    for grp, prim, sec in mirrors:
        mirrored_targets.update([prim, sec])
        node_id_prim = targets.get(prim, "?")
        node_id_sec = targets.get(sec, "?")
        host_prim = nodes.get(node_id_prim, "Unknown")
        host_sec = nodes.get(node_id_sec, "Unknown")
        
        print(f"  ▼ (Grp {grp}) Buddy Mirror HA")
        print_node_details(host_prim, node_id_prim, prim, capacities, networks, is_ha=False)
        print_node_details(host_sec, node_id_sec, sec, capacities, networks, is_ha=False)
        print("  │")

    for tid, nid in targets.items():
        if tid not in mirrored_targets:
            hostname = nodes.get(nid, "Unknown")
            net = networks.get(hostname, {})
            ip = net.get('ip')
            
            if ip and is_pacemaker_active(ip):
                print(f"  ▼ (Pacemaker HA) Alta Disponibilidade via OS")
                print_node_details(hostname, nid, tid, capacities, networks, is_ha=True)
            else:
                print(f"  ▼ (Standalone) Sem Alta Disponibilidade")
                print_node_details(hostname, nid, tid, capacities, networks, is_ha=False)
            print("  │")


def draw_clients():
    """Desenha a topologia exclusiva para os clientes BeeGFS registrados."""
    print("\n" + "#"*80)
    print(" B E E G F S   C L I E N T   A U D I T O R")
    print("#"*80)
    
    print(f"\n[CLIENT TIER]")
    print("=" * 80)
    
    nodes = get_nodes("client")
    if not nodes:
        print("  [!] Nenhum cliente BeeGFS detectado ou registrado.")
        print("\n" + "#"*80 + "\n")
        return

    print(f"  Total de Clientes Registrados: {len(nodes)}\n")
    for node_id, hostname in sorted(nodes.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        print(f"  ├─ [ {hostname} ] (Node ID: {node_id})")
    print("  └─ Fim da lista.\n")
    print("#"*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Auditor de Infraestrutura BeeGFS")
    parser.add_argument('--show-clients', action='store_true', help='Lista todos os clientes BeeGFS registrados na gerência')
    args = parser.parse_args()

    if args.show_clients:
        draw_clients()
        return

    print("\n" + "#"*80)
    print(" B E E G F S   I N F R A S T R U C T U R E   A U D I T O R")
    print("#"*80)
    
    mgmt_host = socket.getfqdn()
    print(f"\n[MANAGEMENT TIER]\n" + "="*80)
    print(f"  [ {mgmt_host} (Serviço Central) ]")

    capacities = get_capacities()
    networks = get_beegfs_network()

    draw_tier("METADATA", "meta", capacities, networks)
    draw_tier("STORAGE", "storage", capacities, networks)
    print("\n" + "#"*80 + "\n")

if __name__ == "__main__":
    main()
