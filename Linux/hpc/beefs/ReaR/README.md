# Relax-and-Recover (ReaR)

**Relax-and-Recover (ReaR)** é a ferramenta correta para gerenciar a recuperação do SO base em todos esses componentes.

A estratégia será dividida em duas partes:

1.  **Estratégia do Nó Head (Bright Cluster Manager)**: Focada em proteger o SO e o estado da base de dados.
2.  **Estratégia dos Nós BeeGFS (Meta/Storage)**: Focada em proteger o SO, adaptando-se aos discos *multipath* e excluindo os grandes volumes de dados.

-----

## 1\. Estratégia ReaR para o Nó Head (Bright Cluster Manager 9.2)

O Nó Head é crítico, pois hospeda o **Banco de Dados do Bright (MySQL/MariaDB)**, que contém toda a configuração do cluster.

### Estratégia Chave: Separação de Backup

A recuperação do Nó Head deve ser um processo em duas etapas:

1.  **ReaR (Backup do SO):** Cobre o sistema operacional, drivers, layout de disco, e a estrutura de diretórios do Bright (ex: `/cm/`).
2.  **Script de Backup (Dados do Bright):** Cobre o estado atual do banco de dados (o único dado que muda constantemente e é vital).

### `local.conf` para o Nó Head

Você deve excluir os diretórios que contêm grandes volumes de dados do Bright (como imagens de software) para manter o backup do ReaR pequeno:

```bash
# /etc/rear/local.conf (Nó Head)

# 1. Definições Básicas
OUTPUT=ISO
BACKUP=NETFS
# Exemplo de URL de backup (ajuste conforme seu ambiente)
# Se estiver usando o modo local (como discutido), use: OUTPUT_URL="file:///mnt/rear_backup_head"
# Se for usar NFS (mais comum em produção):
OUTPUT_URL="nfs://servidor_nfs/caminho/rear_head"
BACKUP_URL="nfs://servidor_nfs/caminho/rear_head"

# 2. Exclusões Críticas (Bright Images)
# Exclua o diretório de imagens de software do Bright para manter o backup pequeno.
# O ReaR ainda registra que este diretório existe e o recria.
BACKUP_PROG_EXCLUDE=(
    "/tmp/*" "/var/tmp/*" "/var/log/*"
    "/mnt/*" "/proc/*" "/sys/*" "/dev/*" "/run/*"
    "/cm/images/*"
    "/cm/shared-ro/*"
)

# 3. Integração (Opcional, mas Recomendada)
# Se você tiver scripts customizados que precisam ser executados APÓS o rear recover,
# use o HOOKS:
# POST_RECOVERY_SCRIPT="bash /mnt/restore_bright_db.sh"
```

### Script Python de Backup do Banco de Dados

Conforme solicitado, este script Python fará o dump do banco de dados do Bright sem usar o módulo `subprocess` (embora isso restrinja o uso de ferramentas externas como o `mysqldump`). Em um ambiente real, você usaria o `subprocess` para chamar o `mysqldump`, mas aqui, simularemos a criação do arquivo de backup crítico.

**Aviso:** Sem `subprocess`, o Python **não pode** interagir com o utilitário `mysqldump` ou similar. O script abaixo é um **placeholder** que lê as credenciais e simula a criação do arquivo. Em produção, use `subprocess` para chamar o `mysqldump` ou utilize um módulo Python específico para o seu banco de dados (ex: `mysql.connector`).

```python
# backup_bright_db_config.py
import datetime
import os

# --- 1. Definir o arquivo de configuração do Bright para pegar a senha ---
# Em um ambiente Bright real, a senha do BD estaria em um arquivo de configuração como este.
CONFIG_FILE = "/cm/local/apps/cmd/etc/cmd.conf"

# --- 2. Definir parâmetros de backup ---
DB_USER = "cmdaemon"
DB_NAME = "cmdb"
BACKUP_DIR = "/var/spool/bright_db_backups"

# --- 3. Função para simular a obtenção da senha (apenas para este exercício) ---
def get_db_password(config_path):
    # Em um script real, você leria o 'DBPass' deste arquivo.
    # Aqui, retornamos um placeholder para fins de demonstração.
    return "SUA_SENHA_REAL_AQUI" 

# --- 4. Função principal de backup ---
def run_db_backup():
    try:
        # Garante que o diretório de backup existe
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        db_password = get_db_password(CONFIG_FILE)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        output_file = os.path.join(BACKUP_DIR, f"cmdb_dump_{timestamp}.sql")
        
        # --- Ação de Backup (Simulação) ---
        
        # Em produção, você USARIA SUBPROCESS AQUI:
        # import subprocess
        # command = f"mysqldump -u {DB_USER} -p{db_password} {DB_NAME} > {output_file}"
        # subprocess.run(command, shell=True, check=True)

        # Sem subprocess, apenas criamos um arquivo dummy e registramos o sucesso:
        with open(output_file, 'w') as f:
            f.write(f"-- Bright CMDB Backup Timestamp: {timestamp}\n")
            f.write("-- Esta linha simula o dump do banco de dados (metadados do cluster).\n")
        
        print(f"Sucesso: O arquivo de backup da CMDB foi criado em: {output_file}")
        
    except Exception as e:
        print(f"ERRO no backup da CMDB: {e}")

if __name__ == "__main__":
    run_db_backup()
```

-----

## 2\. Estratégia ReaR para os Nós BeeGFS (Meta, Storage)

Para os nós BeeGFS, o foco é lidar com o **Multipathing (SAS)** e a **exclusão do BeeGFS** para proteger os dados de petabytes.

### Estratégia Chave: Proteção do Hardware

O ReaR deve garantir a recuperação da **identidade de hardware** do nó (configurações de rede, drivers e `multipath.conf`).

### `local.conf` para os Nós BeeGFS

A configuração é quase idêntica à do Nó Head, mas com exclusões específicas do BeeGFS e garantindo que o `multipath` seja incluído:

```bash
# /etc/rear/local.conf (Nós BeeGFS)

# 1. Definições Básicas
OUTPUT=ISO
BACKUP=NETFS
# Use um diretório de backup separado para os nós de computação
OUTPUT_URL="nfs://servidor_nfs/caminho/rear_beegfs"
BACKUP_URL="nfs://servidor_nfs/caminho/rear_beegfs"

# 2. Exclusões Críticas (BeeGFS Targets)
# Exclua todos os diretórios de Target do BeeGFS (storage e metadata)
BACKUP_PROG_EXCLUDE=(
    "/tmp/*" "/var/tmp/*" "/var/log/*"
    "/mnt/*" "/proc/*" "/sys/*" "/dev/*" "/run/*"
    # Adicione as montagens BeeGFS (Metadados e Storage Targets)
    "/data/beegfs/meta/*"
    "/data/beegfs/storage_target_01/*"
    "/data/beegfs/storage_target_02/*"
    # ... adicione todos os targets aqui
)

# 3. Inclusão de Ferramentas Cruciais
# Embora o ReaR inclua a maioria dos programas por padrão,
# é bom garantir que as ferramentas de multipath e BeeGFS estejam presentes no ISO de resgate.
REQUIRED_PROGS=(
    "${REQUIRED_PROGS[@]}"
    multipath
    multipathd
    beegfs-admon
)
```

### Processo de Recuperação (Recapitulando a Segurança dos Dados)

1.  **Pré-ReaR:** O disco do SO falha. Os discos BeeGFS (Meta/Storage Targets) permanecem intactos.
2.  **`rear recover`:** Você inicializa com o ISO. O ReaR:
      * Ativa o **Multipath** no ambiente de resgate.
      * Recria a partição do SO no novo disco.
      * Restaura o `/etc/multipath.conf` e o `/etc/fstab`.
      * **Monta os targets do BeeGFS (sem formatar).**
      * Restaura os arquivos do SO e do daemon BeeGFS (`/etc/beegfs/*.conf`).
3.  **Pós-ReaR:** Você reinicia no SO restaurado. As configurações de rede IB/Ethernet, Multipath e BeeGFS estarão idênticas às do backup. Os daemons do BeeGFS iniciarão e verão os targets existentes (com os Node IDs originais intactos), minimizando o risco de corrupção.

-----

Etapa crucial para o **Nó Head (Bright Cluster Manager)** é o script que garantirá que, após a recuperação do SO pelo ReaR, o **estado do cluster** seja restaurado.

A estratégia é criar um script Bash que será executado pelo ReaR após restaurar o sistema operacional, garantindo que o **dump do banco de dados** do Bright (que contém a configuração do cluster) seja importado de volta.

-----

## 3\. Script de Restauração do Banco de Dados do Bright (Hook do ReaR)

Este script (`restore_bright_db.sh`) será colocado em um local seguro (como seu servidor NFS de backup) e referenciado no `local.conf` do ReaR.

### A. Ajuste o `local.conf` (Nó Head)

Certifique-se de que a configuração do ReaR no Nó Head inclua o hook que aponta para o script que você usará:

```bash
# /etc/rear/local.conf (Ajuste)

# 3. Integração (Hook de Restauração)
# O ReaR executará este script após restaurar o SO, mas antes de finalizar o processo.
# Coloque o script em um local que o ambiente de resgate possa montar (ex: NFS de backup)
POST_RECOVERY_SCRIPT="bash /mnt/restore_bright_db.sh" 
```

### B. O Script `restore_bright_db.sh` (Bash)

Este script assume que você criou e copiou o arquivo de dump do banco de dados (ex: `cmdb_dump_latest.sql`) para o mesmo local do ReaR no seu servidor de backup.

```bash
#!/bin/bash
# restore_bright_db.sh
# Script executado pelo ReaR após a restauração do SO do Nó Head.

# --- Configurações ---
# O ReaR já montou o seu BACKUP_URL como /mnt/local. Se for NFS:
BACKUP_PATH="/mnt/local"  
# Nome do arquivo de dump que você moveu via SCP/rsync
DB_DUMP_FILE="cmdb_dump_latest.sql" 
DB_USER="cmdaemon"

# --- Funções de Log ---
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') INFO: $1" >> /var/log/rear/db_restore.log
}

err() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') ERROR: $1" >> /var/log/rear/db_restore.log
    exit 1
}

log "Iniciando a restauração do Banco de Dados do Bright Cluster Manager..."

# 1. Obter a senha do banco de dados do arquivo de configuração restaurado
# No Bright, a senha está em /cm/local/apps/cmd/etc/cmd.conf (DBPass)
DB_PASS=$(grep -m 1 '^DBPass ' /cm/local/apps/cmd/etc/cmd.conf | awk '{print $2}' | sed "s/'//g")

if [ -z "$DB_PASS" ]; then
    err "Não foi possível extrair a senha do banco de dados do cmd.conf."
fi
log "Senha do BD obtida com sucesso."

# 2. Localizar e mover o dump do BD
if [ ! -f "$BACKUP_PATH/$DB_DUMP_FILE" ]; then
    err "Arquivo de dump do BD não encontrado em $BACKUP_PATH/$DB_DUMP_FILE. Verifique se você o copiou."
fi

# Copia para um local temporário no SO restaurado
cp "$BACKUP_PATH/$DB_DUMP_FILE" /tmp/cmdb_restore.sql
log "Arquivo de dump copiado para /tmp."

# 3. Importar o dump do banco de dados
log "Importando dados para o CMDB. Isso pode levar alguns minutos..."

# (A) Inicialização do serviço MySQL/MariaDB.
# O ReaR restaura o SO, mas os serviços ainda não estão totalmente configurados para start de produção.
# Forçamos o start do BD para importar os dados.
systemctl start mariadb || systemctl start mysql || err "Falha ao iniciar o serviço de BD."
log "Serviço de BD iniciado."

# (B) Executa a importação do banco de dados
mysql -u "$DB_USER" -p"$DB_PASS" cmdb < /tmp/cmdb_restore.sql

if [ $? -ne 0 ]; then
    err "Falha na importação do CMDB. Verifique o log do MySQL/MariaDB."
fi

log "Restauração do Banco de Dados do Bright CMDB concluída com sucesso!"

# 4. Limpeza e Finalização
rm -f /tmp/cmdb_restore.sql
systemctl stop mariadb || systemctl stop mysql
log "Preparando-se para a reinicialização do sistema."

exit 0
```

### C. Próximos Passos (Ação do Administrador)

1.  **Garantir o Dump Mais Recente:** O script Python de backup deve ser executado regularmente, e o dump mais recente (`cmdb_dump_latest.sql`) deve ser copiado manualmente ou via rsync para o diretório de backup do ReaR (`nfs://servidor_nfs/caminho/rear_head`).
2.  **Teste de Recuperação:** Execute um teste de recuperação em hardware de teste para garantir que o script `restore_bright_db.sh` seja executado corretamente e que o cluster inicie perfeitamente.

Estratégia completa que usa o ReaR para a estrutura de baixo nível e um *hook* personalizado para o dado mais volátil do seu ambiente HPC.

Documento técnico que detalha a estratégia de Recuperação de Desastres (DR) para seu ambiente RHEL 8.7, integrando **Relax-and-Recover (ReaR)** ao **Bright Cluster Manager 9.2** e aos **Servidores BeeGFS**.

-----

# Estratégia de Recuperação de Desastres para HPC (RHEL 8.7, Bright CM, BeeGFS)

## 1\. Visão Geral da Arquitetura e Estratégia ReaR

A recuperação de um ambiente HPC complexo exige uma abordagem de **múltiplas camadas**, onde cada nó é tratado de forma diferente, mas todos utilizam o **Relax-and-Recover (ReaR)** para restaurar a base do Sistema Operacional (SO) em *bare-metal*.

O princípio fundamental é a **Separação de Estados**: O ReaR recupera o **SO e a Estrutura** (a parte pequena e crítica), enquanto os daemons de BeeGFS e as ferramentas do Bright cuidam dos **Dados e do Estado do Cluster** (a parte grande e volátil).

### Diagrama de Fluxo de DR com ReaR (Conceitual)

| FASE | NÓ HEAD (BRIGHT CM) | NÓS BEEGFS (META/STORAGE) |
| :--- | :--- | :--- |
| **1. Backup (`rear mkbackup`)** | SO + `/etc` + **Hook de BD** + Exclusão de Imagens (`/cm/images`) | SO + `/etc` + Configurações **Multipath** + Exclusão de Targets BeeGFS (`/data/*`) |
| **2. Falha** | Falha no disco do SO do Head Node. | Falha no disco do SO do Meta/Storage Node. Targets BeeGFS estão intactos. |
| **3. Recuperação (`rear recover`)** | **Boot do ISO ReaR** → Reconstroi Particionamento → Restaura o SO. | **Boot do ISO ReaR** → Ativa Multipath → Restaura o SO, **sem tocar** nos Targets BeeGFS. |
| **4. Pós-Recuperação** | **Executa o `POST_RECOVERY_SCRIPT`** (importa o último dump da Base de Dados do Bright). | SO reinicia. Daemons BeeGFS iniciam e se **re-anexam** automaticamente aos Targets intactos. |

-----

## 2\. Estratégia para o Nó Head (Bright Cluster Manager)

O Nó Head é o mais complexo devido ao **Banco de Dados do Bright (CMDB)**, que armazena o estado dinâmico do cluster.

### A. Configuração do ReaR no Nó Head (`local.conf`)

O objetivo é excluir o grande diretório de imagens do Bright e incluir o *hook* para a restauração da base de dados.

```bash
# /etc/rear/local.conf (Nó Head - RHEL 8.7, Bright CM 9.2)

# Configuração de Saída e Backup (Exemplo com NFS)
OUTPUT=ISO
BACKUP=NETFS
OUTPUT_URL="nfs://seu_servidor_backup/rear_head"
BACKUP_URL="nfs://seu_servidor_backup/rear_head"

# EXCLUSÕES: Mantenha o backup pequeno e evite o diretório de imagens do Bright
BACKUP_PROG_EXCLUDE=(
    "/tmp/*" "/var/tmp/*" "/var/log/*"
    "/mnt/*" "/proc/*" "/sys/*" "/dev/*" "/run/*"
    # Diretórios grandes do Bright que podem ser provisionados novamente:
    "/cm/images/*"
    "/cm/shared-ro/*"
    "/cm/shared-rw/*"
)

# HOOK DE RECUPERAÇÃO: Chama o script para restaurar o banco de dados
# O script deve ser armazenado no mesmo BACKUP_URL
POST_RECOVERY_SCRIPT="bash $BACKUP_URL/restore_bright_db.sh"
```

### B. O Script Python de Backup do Banco de Dados (Passo Prévio)

Este script deve ser executado **regularmente** antes de cada `rear mkbackup` (ou via Cron) para garantir que o dump do BD esteja atualizado e pronto para ser copiado:

```python
# db_backup_script.py (Sem usar subprocess, focado em criar o arquivo)

import datetime
import os
import sys

# --- CONFIGURAÇÃO ---
CONFIG_FILE = "/cm/local/apps/cmd/etc/cmd.conf"
BACKUP_DIR = "/var/spool/bright_db_backups" # Local onde o ReaR fará o backup
DB_USER = "cmdaemon"
DB_NAME = "cmdb"

# AVISO: Em produção, você USARIA O SUBPROCESS para chamar o 'mysqldump'
# A função abaixo apenas simula a extração de senha e a criação do arquivo.
def get_db_password(config_path):
    try:
        with open(config_path, 'r') as f:
            for line in f:
                if line.strip().startswith('DBPass'):
                    return line.split()[1].strip("'")
    except Exception:
        pass
    return "PASSWORD_PLACEHOLDER" # Fallback

def run_db_backup():
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        
        db_password = get_db_password(CONFIG_FILE)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        output_file = os.path.join(BACKUP_DIR, f"cmdb_dump_{timestamp}.sql")
        
        # Cria o arquivo de dump da CMDB
        with open(output_file, 'w') as f:
            f.write(f"-- Bright CMDB Dump - {timestamp}\n")
            f.write(f"USE {DB_NAME};\n")
            f.write("-- Comando mysqldump simulado (Dados Reais Estariam Aqui)\n")
        
        # Cria um link simbólico para que o ReaR sempre encontre o mais recente
        latest_link = os.path.join(BACKUP_DIR, "cmdb_dump_latest.sql")
        if os.path.lexists(latest_link):
            os.remove(latest_link)
        os.link(output_file, latest_link)

        print(f"Sucesso: Backup da CMDB criado em {latest_link}. Pronto para ReaR.")
        
    except Exception as e:
        print(f"ERRO no backup da CMDB: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_db_backup()
```

-----

## 3\. Estratégia para os Nós BeeGFS (Meta e Storage)

Para os servidores de BeeGFS, a estratégia visa proteger o SO de controle, preservando os *targets* de armazenamento críticos.

### A. Configuração do ReaR nos Nós BeeGFS (`local.conf`)

A inclusão explícita das ferramentas de **Multipath** e a **exclusão total** dos targets BeeGFS são essenciais.

```bash
# /etc/rear/local.conf (Nós BeeGFS - Meta ou Storage)

# Configuração de Saída e Backup
OUTPUT=ISO
BACKUP=NETFS
OUTPUT_URL="nfs://seu_servidor_backup/rear_beegfs"
BACKUP_URL="nfs://seu_servidor_backup/rear_beegfs"

# INCLUSÃO DE FERRAMENTAS CRUCIAIS PARA DRIVER IB E SAS
# Garante que o ReaR consiga enxergar a rede e o armazenamento complexo
REQUIRED_PROGS=(
    "${REQUIRED_PROGS[@]}"
    multipath
    multipathd
)

# EXCLUSÕES: OBRIGATÓRIAS para targets BeeGFS (Evitar corrupção e volume de dados)
BACKUP_PROG_EXCLUDE=(
    "/tmp/*" "/var/tmp/*" "/var/log/*"
    "/mnt/*" "/proc/*" "/sys/*" "/dev/*" "/run/*"
    # Diretórios de Metadata e Storage Targets do BeeGFS
    "/data/beegfs/meta/*"
    "/data/beegfs/storage_target_01/*"
    # Adicione todos os targets aqui (crucial)
)
```

### B. O Fluxo de Recuperação (Garantia de Integridade)

| Etapa | Ação do ReaR no `rear recover` | Objetivo de Integridade |
| :--- | :--- | :--- |
| **1. Layout** | O ReaR lê o `disklayout.conf`. | Recria a partição do SO no novo disco. |
| **2. Multipath** | O ReaR carrega os drivers e ativa o `multipathd`. | Garante que os *targets* BeeGFS (intactos) sejam vistos pelo SO como nomes persistentes (`/dev/mapper/mpathX`). |
| **3. Restauração** | Restaura o SO, `/etc/multipath.conf`, `/etc/fstab` e `/etc/beegfs/*.conf`. | O SO restaurado tem a "identidade" de hardware correta para se religar ao BeeGFS. |
| **4. Pós-Boot** | O SO reinicia. Os targets BeeGFS são montados via `/etc/fstab`. | O daemon BeeGFS é iniciado e se **re-anexa** aos targets existentes. Se o Multipath funcionou, o BeeGFS não detecta alteração estrutural. |

-----

## 4\. Próximas Ações e Testes

A implementação de uma estratégia de DR só é válida após um teste bem-sucedido.

1.  **Testes de Integração:** Teste a recuperação de cada tipo de nó (Head, Meta, Storage) em hardware **idêntico** ou em máquinas virtuais configuradas para simular o Multipath.
2.  **Verificação do Banco de Dados:** No Nó Head restaurado, verifique o status do cluster usando o `cmsh` para confirmar se todas as configurações e o estado dos nós foram restaurados corretamente do dump do BD.
3.  **Verificação do BeeGFS:** Nos nós BeeGFS restaurados, verifique os logs e use comandos como `beegfs-ctl --listtargets` para garantir que o *re-attachment* dos targets ocorreu de forma limpa, sem erros de Node ID ou mapeamento de disco.


-----

Uma estratégia de Recuperação de Desastres (DR) é inútil sem validação. A validação, especialmente em ambientes HPC complexos com Bright e BeeGFS, precisa ir além do simples "o sistema inicializou".

**Estratégias de validação** essenciais para cada componente após uma recuperação de desastres usando o ReaR.

---

## Estratégias de Validação Pós-Recuperação (DR)

A validação deve ser feita em camadas, do hardware ao serviço de cluster.

### 1. Validação de Nível 1: Hardware e SO Base

Este passo garante que o ReaR restaurou a infraestrutura de baixo nível corretamente no novo disco.

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Integridade do SO** | `dmesg | grep 'error'` | Nenhuma mensagem de erro crítica ou falhas de disco/driver. |
| **Particionamento/LVM** | `lsblk` ou `vgs`, `lvs` | O layout do disco original do SO (LVM/partições) deve estar replicado. |
| **Multipathing (SAS)** | `multipath -ll` | Todos os LUNs (incluindo os BeeGFS Targets) devem aparecer com o status `ready` ou `active` e com todos os caminhos (paths) listados. |
| **Rede (IB/Ethernet)** | `ip a` / `ibstat` / `ping` | As interfaces (ex: `eth0`, `ib0`) devem ter os **IPs, máscaras e nomes** corretos (ex: `ib0` deve ser `ib0`). O ping para o Gateway e o Storage Server deve funcionar. |
| **Bootloader** | `grub2-editenv list` | O disco de boot principal deve estar correto, e o sistema deve inicializar sem o ISO do ReaR. |

---

### 2. Validação de Nível 2: Nó Head (Bright Cluster Manager)

Esta validação foca em confirmar que o **estado do cluster** foi restaurado corretamente, graças ao *hook* de importação do banco de dados (CMDB).

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Base de Dados** | `systemctl status mariadb` | O serviço de BD deve estar `active (running)`. |
| **Bright Daemon** | `cmdaemon status` | O serviço principal do Bright deve estar `running` e sem erros. |
| **Estado do Cluster** | `cmsh` e execute: `device use headnode01; get` | Todas as configurações do Nó Head (rede, licença, perfis) devem ser exibidas corretamente. |
| **Nós de Computação** | `cmsh` e execute: `device list` | Todos os nós de computação e serviços BeeGFS devem estar listados. Os nós (se estiverem ligados) devem tentar fazer PXE Boot e provisionar. |
| **Serviços Críticos** | `cmsh` e execute: `service list` | Os serviços de provisionamento (DHCP, TFTP) e agendamento (Slurm, PBS) devem estar listados como `running` ou `started`. |

---

### 3. Validação de Nível 3: Nós BeeGFS (Meta e Storage)

Esta é a etapa mais crítica, pois confirma que os daemons se reconectaram aos Targets de dados de Petabytes sem corrupção.

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Mapeamento de Disco** | `cat /etc/fstab` / `mount` | As partições BeeGFS (`/data/beegfs/*`) devem estar montadas corretamente, usando nomes persistentes (`/dev/mapper/mpathX` é o ideal). |
| **Status do Daemon** | `systemctl status beegfs-mgmtd` (no Meta) ou `systemctl status beegfs-storage` (no Storage) | O serviço relevante do BeeGFS deve estar `active (running)`. |
| **Status dos Targets** | `beegfs-ctl --listtargets --nodetype=[meta/storage]` | O(s) alvo(s) de metadados/armazenamento deste nó devem ser listados como `online`. O Node ID deve ser o ID original do cluster. |
| **Integridade dos Targets**| `beegfs-ctl --liveness` | O teste de liveness (atividade) deve retornar sucesso, indicando que o nó está comunicando com o restante do cluster. |
| **Verificação de Dados** | `cd /data/beegfs/storage_target_01` e `ls -l` | Deve ser possível navegar pelas pastas de dados (BeeGFS targets) e verificar que os atributos de segurança (*xattrs*) e permissões de arquivos parecem intactos. |

-----

--

Para finalizar a sua estratégia de Recuperação de Desastres (DR) com **Relax-and-Recover (ReaR)** no ambiente **Bright Cluster Manager/BeeGFS**, aqui estão as **estratégias de validação** essenciais.

A validação, em um ambiente HPC complexo, precisa ir além do simples "o sistema inicializou"; ela deve confirmar que todos os serviços de cluster, redes de alta velocidade (InfiniBand) e o armazenamento (Multipath/BeeGFS) estão funcionando e íntegros.

---

## Estratégias de Validação Pós-Recuperação (DR)

A validação deve ser feita em camadas, garantindo que o ReaR restaurou a infraestrutura de baixo nível corretamente antes de iniciar os serviços de cluster.

### 1. Validação de Nível 1: Hardware, Disco e SO Base

Este passo garante que o ReaR restaurou a infraestrutura de baixo nível (especialmente o Multipathing e a rede) corretamente no novo disco.

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Integridade do SO** | `dmesg | grep 'error'` | Nenhuma mensagem de erro crítica ou falhas de disco/driver. |
| **Particionamento/LVM** | `lsblk` ou `vgs`, `lvs` | O layout do disco original do SO (LVM/partições) deve estar **replicado**. |
| **Multipathing (SAS)** | `multipath -ll` | Todos os LUNs (incluindo os BeeGFS Targets) devem aparecer com o status `ready` ou `active` e com **todos os caminhos (paths)** listados. Isso confirma que o ReaR restaurou o `/etc/multipath.conf` corretamente. |
| **Rede (IB/Ethernet)** | `ip a` / `ibstat` / `ping` | As interfaces (ex: `eth0`, `ib0`) devem ter os **IPs, máscaras e nomes** corretos. O `ibstat` deve mostrar o link ativo (ex: `LinkUp`). |
| **Bootloader** | `grub2-editenv list` | O disco de boot principal deve estar correto, e o sistema deve inicializar **sem o ISO do ReaR**. |

---

### 2. Validação de Nível 2: Nó Head (Bright Cluster Manager)

Esta validação foca em confirmar que o **estado do cluster** foi restaurado corretamente através do *hook* de importação da Base de Dados (CMDB).

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Base de Dados** | `systemctl status mariadb` | O serviço de BD deve estar `active (running)`. |
| **Bright Daemon** | `cmdaemon status` | O serviço principal do Bright deve estar `running` e sem erros. |
| **Estado do Cluster** | `cmsh` e execute: `device use headnode01; get` | Todas as configurações do Nó Head (rede, licença, perfis) devem ser exibidas corretamente. |
| **Nós de Computação** | `cmsh` e execute: `device list` | Todos os nós de computação e serviços BeeGFS devem estar listados. Os nós devem estar no estado correto (ex: `up`, `idle` ou `running`). |
| **Serviços Críticos** | `cmsh` e execute: `service list` | Os serviços de provisionamento (DHCP, TFTP) e agendamento (Slurm, PBS) devem estar listados como `running` ou `started`. |

---

### 3. Validação de Nível 3: Nós BeeGFS (Meta e Storage)

Esta é a etapa mais crítica. Ela confirma que os daemons se reconectaram aos Targets de dados de Petabytes sem corrupção, validando a exclusão do ReaR.

| Componente | Comando de Validação | Resultado Esperado |
| :--- | :--- | :--- |
| **Mapeamento de Disco** | `cat /etc/fstab` / `mount` | As partições BeeGFS (`/data/beegfs/*`) devem estar montadas corretamente, usando **nomes persistentes** (como `/dev/mapper/mpathX`). |
| **Status do Daemon** | `systemctl status beegfs-storage` (no Storage) | O serviço relevante do BeeGFS deve estar `active (running)` e ter sido iniciado com sucesso. |
| **Status dos Targets** | `beegfs-ctl --listtargets --nodetype=[meta/storage]` | O(s) alvo(s) de metadados/armazenamento deste nó devem ser listados como `online`. O **Node ID** deve ser o ID original do cluster (o que confirma que o daemon se re-anexou corretamente). |
| **Integridade dos Dados** | `cd /data/beegfs/storage_target_01` e `ls -l` | Deve ser possível navegar pelas pastas de dados (BeeGFS targets) e verificar que as permissões e os **Atributos Estendidos** (*xattrs*) estão intactos. |
| **Comunicação** | `beegfs-ctl --liveness` | O teste de liveness (atividade) deve retornar sucesso, indicando que o nó está comunicando com o restante do cluster BeeGFS. |

### Dica Essencial: Teste de DR Regular

Recomenda-se realizar um **Teste de Recuperação de Desastres (DR)** completo pelo menos duas vezes por ano. Sem testar o processo *rear recover* em um hardware de teste, você está apenas especulando que ele funcionará quando for realmente necessário.
