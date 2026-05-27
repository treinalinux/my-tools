## BEEGFS INFRASTRUCTURE AUDITOR (beegfs-topology.py)

O **BEEGFS INFRASTRUCTURE AUDITOR** (**beegfs-topology.py**) deve ser executado no o **servidor management (servidor que roda o beegfs-mgmtd)** infraestrutura do BeeGFS desconhecida, com isso após ser executado irá fornecer os da infraestrutura do BeeGFS, acredito que vai reduzir o tempo de checagens.
No futuro certamente farei melhorias no **beegfs-topology.py**, até porque criei e rodei em um laboratório, mas não criei ele para o laboratório e sim, fiz a criação o tentando deixar mais genérico possível.

## Checar uma infraestrutura do BeeGFS desconhecida

Para checar uma infraestrutura do BeeGFS que você acaba de conhecer, é necessário que o **beegfs-topology.py** seja levado para o **servidor management (servidor que roda o beegfs-mgmtd)** e que tenha realizado a distribuição da chave ssh entre os servidores.

```bash

[root@bee-mgt ansible-prd]# ./beegfs-topology.py 

################################################################################
 B E E G F S   I N F R A S T R U C T U R E   A U D I T O R
################################################################################

[MANAGEMENT TIER]
================================================================================
  [ bee-mgt.empresa.corp (Serviço Central) ]

[METADATA TIER]
================================================================================
  ▼ (Pacemaker HA) Alta Disponibilidade via OS
    ├─ [ bee-meta-ha ] (Node: 1 | Target: 1)
    │    ├─ Rede App:   192.168.122.201:8005 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 37.7GiB livre de 40.0GiB
    │    ├─ Hardware:   Block Storage Remoto -> 0x1af4,LIO-ORG disk_meta iscsi [2 conexões] (Targets: 192.168.122.250:3260)
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
    │    └─ [ Integração Pacemaker HA ]
    │         ├─ Nós Físicos:   Online: bee-meta01.priv.empresa.corp bee-meta02.priv.empresa.corp
 Online:
    │         ├─ Interface VIP: VIP [192.168.122.150] associado ao recurso meta_vip
    │         ├─ Área Ofertada: Device: /dev/mapper/mpatha ➔ Montado em: /mnt/shared_meta
    │         ├─ Recursos Ativos SO:
    │         │    ├─ * Resource Group: meta_group:
    │         │    ├─ * meta_vip (ocf::heartbeat:IPaddr2): Started bee-meta01.priv.empresa.corp
    │         │    ├─ * meta_fs (ocf::heartbeat:Filesystem): Started bee-meta01.priv.empresa.corp
    │         │    ├─ * meta_service (systemd:beegfs-meta): Started bee-meta01.priv.empresa.corp
    │         └─ Restrições de Ordem: Nenhuma configurada
  │

[STORAGE TIER]
================================================================================
  ▼ (Pacemaker HA) Alta Disponibilidade via OS
    ├─ [ bee-str-a-ha ] (Node: 1 | Target: 1)
    │    ├─ Rede App:   192.168.122.203:8003 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 37.7GiB livre de 40.0GiB
    │    ├─ Hardware:   Block Storage Remoto -> 0x1af4,LIO-ORG disk_str_a iscsi [2 conexões] (Targets: 192.168.122.250:3260)
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
    │    └─ [ Integração Pacemaker HA ]
    │         ├─ Nós Físicos:   Online: bee-str01.priv.empresa.corp bee-str03.priv.empresa.corp
 Online:
    │         ├─ Interface VIP: VIP [192.168.122.151] associado ao recurso stra_vip
    │         ├─ Área Ofertada: Device: /dev/mapper/mpatha ➔ Montado em: /mnt/shared_storage01
    │         ├─ Recursos Ativos SO:
    │         │    ├─ * Resource Group: stra_group:
    │         │    ├─ * stra_vip (ocf::heartbeat:IPaddr2): Started bee-str01.priv.empresa.corp
    │         │    ├─ * stra_fs (ocf::heartbeat:Filesystem): Started bee-str01.priv.empresa.corp
    │         │    ├─ * stra_service (systemd:beegfs-storage): Started bee-str01.priv.empresa.corp
    │         └─ Restrições de Ordem: Nenhuma configurada
  │
  ▼ (Pacemaker HA) Alta Disponibilidade via OS
    ├─ [ bee-str-b-ha ] (Node: 2 | Target: 2)
    │    ├─ Rede App:   192.168.122.204:8003 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 37.7GiB livre de 40.0GiB
    │    ├─ Hardware:   Block Storage Remoto -> 0x1af4,LIO-ORG disk_str_b iscsi [2 conexões] (Targets: 192.168.122.250:3260)
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
    │    └─ [ Integração Pacemaker HA ]
    │         ├─ Nós Físicos:   Online: bee-str02.priv.empresa.corp bee-str04.priv.empresa.corp
 Online:
    │         ├─ Interface VIP: VIP [192.168.122.152] associado ao recurso strb_vip
    │         ├─ Área Ofertada: Device: /dev/mapper/mpatha ➔ Montado em: /mnt/shared_storage02
    │         ├─ Recursos Ativos SO:
    │         │    ├─ * Resource Group: strb_group:
    │         │    ├─ * strb_vip (ocf::heartbeat:IPaddr2): Started bee-str02.priv.empresa.corp
    │         │    ├─ * strb_fs (ocf::heartbeat:Filesystem): Started bee-str02.priv.empresa.corp
    │         │    ├─ * strb_service (systemd:beegfs-storage): Started bee-str02.priv.empresa.corp
    │         └─ Restrições de Ordem: Nenhuma configurada
  │

################################################################################

```

## Checar os clientes da infraestrutura do BeeGFS

O **beegfs-topology.py** também pode ser usado para checar os clientes BeeGFS da infraestrutura, mas nesse caso **não é necessário** distribuição da chave ssh entre os servidores.

Você pode usar a opção **-h** ou **--help** para consultar as opções disponíveis. Na versão atual, temos apenas uma opção que é para consultar os clientes.

```bash

[root@bee-mgt ansible-prd]# ./beegfs-topology.py -h
usage: beegfs-topology.py [-h] [--show-clients]

Auditor de Infraestrutura BeeGFS

optional arguments:
  -h, --help      show this help message and exit
  --show-clients  Lista todos os clientes BeeGFS registrados na gerência

```

Checando os clientes da infraestrutura do BeeGFS

```

[root@bee-mgt ansible-prd]# ./beegfs-topology.py --show-clients

################################################################################
 B E E G F S   C L I E N T   A U D I T O R
################################################################################

[CLIENT TIER]
================================================================================
  Total de Clientes Registrados: 1

  ├─ [ 73C0-6A15F0AF-bee-mgt.empresa.corp ] (Node ID: 2)
  └─ Fim da lista.

################################################################################

```
