
Crie o diretório base e o arquivo de configuração.

```bash

mkdir -p /opt/beegfs_backup
vim /opt/beegfs_backup/backup_config.json

```

Escolha o qual perfil do nó realizar backup "management", "metadata", "storage", "all". Exemplo:

```bash

[root@bee-mgt ansible-prd]# ./beegfs_backup.py management

[20260526_181928] Avaliando backup do tier: MANAGEMENT
------------------------------------------------------------
  [+] Copiado: /etc/beegfs
  [+] Copiado: /opt/beegfs_backup/backup_config.json
  [+] Copiado: /etc/openldap/ldap.conf
  [+] Copiado: /etc/sssd/sssd.conf
  [+] Copiado: /root/.bashrc
------------------------------------------------------------
[OK] Novo backup gerado: /mnt/backups/beegfs_configs/backup_management_bee-mgt.empresa.corp_20260526_181928.tar.gz (25.7 KB)

[root@bee-mgt ansible-prd]# ./beegfs_backup.py management

[20260526_181935] Avaliando backup do tier: MANAGEMENT
------------------------------------------------------------
  [SKIPPED] Nenhuma alteração detectada. Backup ignorado para economizar disco.

```
