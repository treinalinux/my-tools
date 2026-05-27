## BEEGFS INFRASTRUCTURE AUDITOR (beegfs-topology.py)

O **BEEGFS INFRASTRUCTURE AUDITOR** (**beegfs-topology.py**) deve ser executado no **servidor management (servidor que roda o beegfs-mgmtd)** infraestrutura do BeeGFS desconhecida, com isso após ser executado irá fornecer os da infraestrutura do BeeGFS, acredito que vai reduzir o tempo de checagens.
No futuro certamente farei melhorias no **beegfs-topology.py**, até porque criei e rodei em um laboratório, mas não criei ele para o laboratório e sim, fiz a criação o tentando deixar mais genérico possível.

## Checar uma infraestrutura do BeeGFS desconhecida

Para checar uma infraestrutura do BeeGFS que você acaba de conhecer, é necessário que o **beegfs-topology.py** seja levado para o **servidor management (servidor que roda o beegfs-mgmtd)** e que tenha realizado a distribuição da chave ssh entre os servidores.

### Checando uma infraestrutura do BeeGFS (Buddy Mirror)

Checando uma infraestrutura do BeeGFS que está configurada com alta disponibilidade usando Buddy Mirror, e os servidores de meta e storage estão com discos locais.

```bash

[root@bee-mgt ~]# ./beegfs-topology.py

################################################################################
 B E E G F S   I N F R A S T R U C T U R E   A U D I T O R
################################################################################

[MANAGEMENT TIER]
================================================================================
  [ bee-mgt.empresa.corp (Serviço Central) ]

[METADATA TIER]
================================================================================
  ▼ (Grp 1) Buddy Mirror HA
    ├─ [ bee-meta01.empresa.corp ] (Node: 2 | Target: 2)
    │    ├─ Rede App:   192.168.122.201:8005 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 6.8GiB livre de 7.1GiB
    │    ├─ Hardware:   Storage Local/Direct -> 0x1af4,QEMU QEMU DVD-ROM sata [3 disco(s)]
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
    ├─ [ bee-meta02.empresa.corp ] (Node: 3 | Target: 3)
    │    ├─ Rede App:   192.168.122.202:8005 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 6.8GiB livre de 7.1GiB
    │    ├─ Hardware:   Storage Local/Direct -> 0x1af4,QEMU QEMU DVD-ROM sata [3 disco(s)]
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
  │

[STORAGE TIER]
================================================================================
  ▼ (Grp 1) Buddy Mirror HA
    ├─ [ bee-str02.empresa.corp ] (Node: 5 | Target: 501)
    │    ├─ Rede App:   192.168.122.204:8003 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 37.6GiB livre de 40.0GiB
    │    ├─ Hardware:   Storage Local/Direct -> 0x1af4,QEMU QEMU DVD-ROM sata [4 disco(s)]
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
    ├─ [ bee-str01.empresa.corp ] (Node: 4 | Target: 401)
    │    ├─ Rede App:   192.168.122.203:8003 | BeeGFS Proto: TCP
    │    ├─ Storage:    ONLINE | 37.6GiB livre de 40.0GiB
    │    ├─ Hardware:   Storage Local/Direct -> 0x1af4,QEMU QEMU DVD-ROM sata [4 disco(s)]
    │    ├─ Rede OS:    Velocidade Virtual/Desconhecida
  │

################################################################################

```

#### BeeGFS (Buddy Mirroring)

O BeeGFS (Buddy Mirroring) é um mecanismo de replicação e alta disponibilidade nativo do sistema de arquivos paralelo BeeGFS, focado em ambientes de computação de alto desempenho (HPC) e IA. [1, 2] 
Ele funciona dividindo os servidores de armazenamento ou metadados em pares (os chamados buddies). O sistema replica os dados de forma transparente entre o nó primário e o seu buddy, garantindo que as informações permaneçam acessíveis mesmo se um dos servidores falhar. [2, 3] 

##### Como funciona e principais vantagens

* Sem dependência de hardware: A replicação é feita inteiramente via software, eliminando a necessidade de storages físicos compartilhados ou controladores RAID complexos.
* Domínios de falha (Failure Domains): Você pode alocar os servidores parceiros em diferentes racks ou até em salas de servidores adjacentes. Isso protege seus dados contra incidentes físicos graves.
* Auto-recuperação (Self-healing): Se um servidor cair, a aplicação continua funcionando sem interrupções através do nó espelhado. Quando o servidor defeituoso retorna, o sistema sincroniza automaticamente apenas o que foi alterado.
* Flexibilidade estrutural: Pode ser aplicado tanto para os servidores de dados quanto para os servidores de metadados. [2, 3, 4] 


##### Pontos de atenção

* Custo de armazenamento: Como os dados são espelhados entre a dupla, a capacidade de armazenamento efetiva do cluster é reduzida pela metade (requer o dobro de discos). [4] 

Você pode gerenciar essas configurações através da linha de comando usando ferramentas como o beegfs-ctl. Para detalhes mais técnicos sobre a configuração, acesse a documentação oficial do [BeeGFS Mirroring](https://doc.beegfs.io/latest/advanced_topics/mirroring.html). [5, 6] 

[1] [https://xinnor.io](https://xinnor.io/solutions/beegfs/)
[2] [https://www.advancedhpc.com](https://www.advancedhpc.com/pages/beegfs)
[3] [https://beegfs-docs.readthedocs.io](https://beegfs-docs.readthedocs.io/en/latest/mirroring.html)
[4] [https://groups.google.com](https://groups.google.com/g/fhgfs-user/c/MNhv0Cl8FgI)
[5] [https://doc.beegfs.io](https://doc.beegfs.io/7.4.2/advanced_topics/mirroring.html)
[6] [https://doc.beegfs.io](https://doc.beegfs.io/latest/advanced_topics/mirroring.html)


### Checando uma infraestrutura do BeeGFS (Pacemaker)

Checando uma infraestrutura do BeeGFS que está configurada com alta disponibilidade usando Pacemaker, e os servidores de meta e storage estão discos de uma servidor remoto iscsi.


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


#### Diferenças entre BeeGFS Buddy Mirror e BeeGFS com Pacemaker

A principal diferença é o escopo da proteção: o Buddy Mirror foca na redundância dos dados e metadados, enquanto o Pacemaker gerencia o failover de serviços e conectividade de rede.
Ambas as soluções são usadas para alta disponibilidade (HA), mas atuam em camadas complementares do cluster.

##### Comparação Direta

A tabela abaixo detalha as diferenças operacionais de cada abordagem:

| Característica | BeeGFS Buddy Mirror | BeeGFS com Pacemaker |
|---|---|---|
| Foco Principal | Replicação física dos arquivos e metadados. | Gerenciamento de processos e IPs virtuais. |
| Como Funciona | Duplica os dados em tempo real entre dois nós (buddies). | Monitora a saúde dos nós e move serviços se um falhar. |
| Uso de Hardware | Requer o dobro de espaço em disco (armazenamento local). | Geralmente exige armazenamento compartilhado (ex: SAN/JBOD). |
| Custo de Rede | Alto (tráfego contínuo para replicar dados escritos). | Baixo (apenas tráfego de monitoramento heartbeat). |
| Cenário de Falha | Se um nó queima, o dado está salvo no nó parceiro. | Se um nó cai, o Pacemaker inicia o serviço no nó reserva. |

##### Quando usar cada um?

* Use o Buddy Mirror se você possui servidores com armazenamento local isolado (sem storage compartilhado) e precisa garantir que a quebra de um disco ou servidor não cause perda de dados.
* Use o Pacemaker se você já possui uma infraestrutura de storage compartilhado de alta resiliência e precisa apenas garantir que o serviço do BeeGFS continue rodando caso o servidor que gerencia o volume pare de responder.

Para cenários críticos de missão contínua, arquitetos de HPC costumam combinar ambos. O Pacemaker gerencia a inicialização e os IPs flutuantes dos serviços, enquanto o Buddy Mirror cuida da integridade dos dados subjacentes.
Se você estiver planejando o design do seu cluster, me informe:

* Qual é o tipo de armazenamento físico disponível (Discos locais ou Storage compartilhado)?
* Qual é o foco principal do projeto (Evitar perda de dados ou maximizar o tempo de atividade dos serviços)?


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

Exemplo de quando não tem clientes registrados.

```bash

[root@bee-mgt ~]# ./beegfs-topology.py --show-clients

################################################################################
 B E E G F S   C L I E N T   A U D I T O R
################################################################################

[CLIENT TIER]
================================================================================
  [!] Nenhum cliente BeeGFS detectado ou registrado.

################################################################################


```
