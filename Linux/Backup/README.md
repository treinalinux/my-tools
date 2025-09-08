
Backup Manager HPC

Visão Geral

O Backup Manager HPC é uma ferramenta de linha de comando em Python, poderosa e flexível, desenhada para automatizar backups e restaurações de configurações em ambientes de servidores Linux. A ferramenta é ideal para gerir clusters e infraestruturas complexas, permitindo backups baseados em papéis, backups de sistema otimizados e restaurações seguras com confirmação.

Funcionalidades Principais

Backups Baseados em Papéis: Defina os papéis de cada servidor (ex: mysql, firewall, beegfs-meta) num ficheiro CSV central.
Múltiplos Modos de Backup:
service: Cria um arquivo de backup para cada serviço/papel de um servidor.
role-agg: Agrega todos os papéis de um servidor num único arquivo de backup.
Backup de Sistema Otimizado (system-full): Realiza um backup completo do sistema de ficheiros, excluindo de forma inteligente diretórios desnecessários (/proc, /tmp, .cache, etc.) para poupar espaço.
Backups Personalizados (custom): Permite fazer backups ad hoc de ficheiros ou diretórios específicos.
Restauração Segura e Seletiva:
Exige dupla confirmação para operações de restauração, prevenindo erros em produção.
Permite restaurar seletivamente apenas os serviços necessários a partir de um backup agregado ou completo.
Extensível: Facilmente extensível para novos tipos de backup através da edição do dicionário de configuração BACKUP_CONFIGS no script.

Pré-requisitos

Antes de usar a ferramenta, garanta que os seguintes requisitos são cumpridos:
Python 3.6+: Instalado na máquina onde o script será executado.
Acesso SSH sem Password: A máquina que executa o script deve ter acesso por chave SSH (sem password) a todos os servidores alvo. Isto é obrigatório para a automação com crontab.
Acesso sudo: O utilizador SSH deve ter permissões sudo sem password nos servidores alvo para executar comandos como tar, racadm e mysqldump.
Dell iDRAC Tools (Opcional): Para usar o papel de backup idrac, as ferramentas racadm devem estar instaladas nos servidores Dell.

Instalação

Guarde o script com o nome backup_manager_hpc.py.
Torne-o executável:
Bash
chmod +x backup_manager_hpc.py



Configuração (servers.csv)

A ferramenta opera com base num ficheiro CSV que define os anfitriões e os seus papéis.
Formato: O ficheiro deve ter duas colunas: hostname e type.
Múltiplos Papéis: Um único servidor pode ter múltiplos papéis. Basta listá-los na coluna type, separados por um ponto e vírgula (;).
Exemplo de servers.csv:

Snippet de código


hostname,type
headnode.cluster.local,system-full;bright;network-services;firewall;idrac
db01.cluster.local,system-full;mysql;idrac;net-bonding
storage01.cluster.local,beegfs-storage;firewall;idrac



Guia de Utilização (Comandos)


Obter Ajuda


Bash


./backup_manager_hpc.py -h
./backup_manager_hpc.py backup -h
./backup_manager_hpc.py restore -h



1. Operação de Backup


Backup via Ficheiro CSV (o mais comum)


Bash


./backup_manager_hpc.py backup csv [ARQUIVO_CSV] [OPÇÕES]


--mode service (padrão): Cria um arquivo .tar.gz para cada papel de cada servidor.
Bash
./backup_manager_hpc.py backup csv servers.csv --mode service --local-dir /mnt/backups/daily


--mode role-agg: Cria um único arquivo .tar.gz por servidor, agregando todos os seus papéis.
Bash
./backup_manager_hpc.py backup csv servers.csv --mode role-agg --local-dir /mnt/backups/weekly



Backup de um Caminho Específico (custom)

Útil para backups rápidos e não planeados.

Bash


./backup_manager_hpc.py backup custom --hostname [HOSTNAME] --path [CAMINHO1] --path [CAMINHO2]


Exemplo:

Bash


./backup_manager_hpc.py backup custom \
  --hostname webserver01 \
  --path /var/www/html \
  --path /etc/nginx/sites-enabled/ \
  --local-dir /mnt/backups/custom



2. Operação de Restauração

A restauração é sempre granular e requer confirmação de segurança.

Restaurar um ou mais Serviços


Bash


./backup_manager_hpc.py restore --hostname [HOSTNAME] --source-file [ARQUIVO_DE_BACKUP] --type [TIPO1] --type [TIPO2]


Exemplo (restaurar Firewall e MySQL a partir de um backup agregado):

Bash


./backup_manager_hpc.py restore \
  --hostname db01.cluster.local \
  --source-file /mnt/backups/weekly/db01.cluster.local/db01.cluster.local_role_agg_backup_20250907-020500.tar.gz \
  --type firewall \
  --type mysql


O script irá pedir que digite db01.cluster.local para confirmar a ação.

Restaurar um Backup Personalizado ou de Sistema

Use o tipo especial custom ou system-full para restaurar todo o conteúdo de um arquivo.

Bash


./backup_manager_hpc.py restore \
  --hostname webserver01 \
  --source-file /mnt/backups/custom/webserver01/webserver01_custom_backup_20250908-080000.tar.gz \
  --type custom



Estratégia de Automação com Crontab (GFS)

A estratégia Grandfather-Father-Son (Avô-Pai-Filho) é um método de rotação de backups que equilibra a retenção de dados com o uso de espaço em disco.
Son (Filho): Backups diários de configurações críticas (retidos por 7 dias).
Father (Pai): Backups semanais completos do sistema e serviços (retidos por 4-5 semanas).
Grandfather (Avô): Arquivos mensais de longo prazo.
Exemplo de Configuração crontab -e:

Snippet de código


# Lembre-se de adaptar os caminhos para o seu ambiente!

# (Filho) Backup DIÁRIO de serviços críticos (executa todos os dias às 01:05)
# Use o modo 'service' para backups rápidos e pequenos de configurações.
5 1 * * * /usr/bin/python3 /opt/scripts/backup_manager_hpc.py backup csv /opt/scripts/servers-diario.csv --mode service --local-dir /mnt/backups/daily/ >> /var/log/backup_script.log 2>&1

# (Filho) Limpeza de backups diários com mais de 7 dias
10 1 * * * find /mnt/backups/daily/ -mtime +7 -exec rm -rf {} \; >> /var/log/backup_script.log 2>&1

# (Pai) Backup SEMANAL completo do sistema (executa todo Domingo às 02:05)
# Use um CSV específico (ex: servers-semanal.csv) que contenha o papel 'system-full'.
5 2 * * 0 /usr/bin/python3 /opt/scripts/backup_manager_hpc.py backup csv /opt/scripts/servers-semanal.csv --mode service --local-dir /mnt/backups/weekly/ >> /var/log/backup_script.log 2>&1

# (Pai) Limpeza de backups semanais com mais de 35 dias (~5 semanas)
10 2 * * 0 find /mnt/backups/weekly/ -mtime +35 -exec rm -rf {} \; >> /var/log/backup_script.log 2>&1

# (Avô) Arquivo MENSAL (executa no primeiro dia do mês às 05:05)
# Recomenda-se um script auxiliar para arquivar o backup semanal mais relevante para um armazenamento de longo prazo.
5 5 1 * * /opt/scripts/archive_monthly_backup.sh >> /var/log/backup_script.log 2>&1



Tabela de Referência de Papéis (type)

Papel (type)
Descrição
beegfs-meta
Configurações e logs de um servidor de Metadados BeeGFS.
beegfs-storage
Configurações de um servidor de Armazenamento BeeGFS.
bright
Configurações do Bright Cluster Manager.
firewall
Configurações de iptables e firewalld.
grafana
Configurações do Grafana e dump do InfluxDB.
idrac
Exportação do Perfil de Configuração do Servidor (SCP) de um Dell iDRAC.
mysql
Dump completo (mysqldump --all-databases) de um servidor MySQL/MariaDB.
net-bonding
Ficheiros de configuração de agregação de links (bonding) para várias distros.
network-services
Configurações de serviços de rede essenciais (DNS, DHCP, NTP).
pacemaker
Configurações de cluster Pacemaker e Corosync.
system-full
Backup otimizado do sistema de ficheiros, excluindo caches e diretórios voláteis.


