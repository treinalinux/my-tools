**Funcionalidades Adicionadas:**

1.  **Exibir Configurações:**
    * `--display-all`: Mostra os valores atuais de todos os parâmetros predefinidos (sysctl e dispositivos).
    * `--display-sysctl CAMINHO`: Mostra o valor atual de um parâmetro sysctl específico.
    * `--display-device DISPOSITIVO PARAMETRO`: Mostra o valor atual de um parâmetro de um dispositivo de bloco específico.
2.  **Alterar Configurações:**
    * `--set-sysctl CAMINHO VALOR`: Define um parâmetro sysctl específico.
    * `--set-device DISPOSITIVO PARAMETRO VALOR`: Define um parâmetro de um dispositivo de bloco específico.
3.  **Aplicar Padrões:**
    * `--apply-defaults`: Aplica o conjunto de otimizações predefinidas (comportamento similar ao script anterior).
4.  **Especificar Dispositivos:**
    * `--devices LISTA_DE_DISPOSITIVOS`: Permite especificar para quais dispositivos as operações `--display-all` ou `--apply-defaults` devem se aplicar (padrão: "sda,sdb").
**Como Usar o Novo Script:**

1.  **Salvar:** Salve como `configure_perf.py` (ou outro nome).
2.  **Permissão:** `chmod +x configure_perf.py`

3.  **Exemplos de Uso:**

    * **Exibir todos os valores atuais predefinidos para `sda` e `sdd`:**
        ```bash
        ./configure_perf.py --display-all --devices sda,sdd
        ```
    * **Exibir valor atual de um sysctl específico:**
        ```bash
        ./configure_perf.py --display-sysctl /proc/sys/vm/dirty_ratio
        ```
    * **Exibir valor atual do agendador de `sdb`:**
        ```bash
        ./configure_perf.py --display-device sdb scheduler
        ```
    * **Definir um sysctl (requer root):**
        ```bash
        sudo ./configure_perf.py --set-sysctl /proc/sys/vm/dirty_background_ratio 10
        ```
    * **Definir agendador de `sdc` para `kyber` (requer root):**
        ```bash
        sudo ./configure_perf.py --set-device sdc scheduler kyber
        ```
    * **Aplicar todas as configurações padrão predefinidas para `sda` e `sdb` (requer root):**
        ```bash
        sudo ./configure_perf.py --apply-defaults --devices sda,sdb
        ```
        (Se `--devices` não for especificado, usará "sda,sdb" por padrão com `--apply-defaults` e `--display-all`).
    * **Obter ajuda:**
        ```bash
        ./configure_perf.py --help
        ```

**Mudanças e Melhorias Chave:**

* **`argparse`:** Para uma interface de linha de comando robusta.
* **Ações Exclusivas:** Usado `add_mutually_exclusive_group` para garantir que apenas uma ação principal (display, set, apply) seja executada por vez.
* **Flexibilidade de Dispositivos:** O argumento `--devices` permite especificar quais dispositivos de bloco são o alvo para as operações em lote (`--display-all`, `--apply-defaults`).
* **Leitura Melhorada:** A função `get_current_value` agora lida melhor com os formatos de saída de `/sys/kernel/mm/transparent_hugepage/*` e `/sys/block/*/queue/scheduler` que usam colchetes para indicar o valor ativo.
* **Feedback:** O script fornece mais feedback sobre o que está fazendo e o estado atual dos parâmetros.
* **Segurança:** Ações que modificam o sistema verificam explicitamente por privilégios de root (embora a escrita nos arquivos `/proc` e `/sys` já falharia sem eles).
* **Padrões Ajustados:** Alterei o padrão para `transparent_hugepage` para `madvise` e `zone_reclaim_mode` para `0` em `SYSCTL_SETTINGS_DEFAULTS` por serem geralmente melhores para HPC, mas o usuário pode alterar isso no dicionário ou via `--set-sysctl`. O `DEVICE_PARAM_DEFAULTS_TEMPLATE` usa `mq-deadline`.
* **Não Sai em Erro de Permissão (Set Individual):** Se um `set_value` individual falhar devido à permissão (porque o usuário esqueceu `sudo` mas tentou uma ação de set), ele agora imprime o erro mas não encerra o script inteiro, a menos que seja no `--apply-defaults` onde a verificação é feita antes.

Este script agora é uma ferramenta muito mais poderosa e interativa!
