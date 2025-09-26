# Documentação e Plano de Ação – BeeGFS Storage em HDD (workload misto)

---

## 1. Contexto

Os servidores BeeGFS-storage no seu cluster HPC usam **HDDs rotacionais** como backend de dados.
O workload é **misto**:

* Arquivos grandes (datasets massivos, checkpoints, streaming).
* Arquivos pequenos (datasets de Machine Learning, metadados).

### Riscos principais

* HDDs são eficientes em streaming, mas sofrem em I/O aleatório.
* Sem otimização, o kernel pode acumular filas muito longas → **latência alta**.
* Perfis do `tuned` podem sobrescrever tunings manuais → é preciso **customizar**.

---

## 2. Ajustes aplicados

### 2.1 Perfil `tuned.conf` final (`beegfs-storage-hdd-mixed`)

📂 `/etc/tuned/beegfs-storage-hdd-mixed/tuned.conf`

```ini
# Perfil Tuned customizado para servidor de armazenamento BeeGFS
# Otimizado para: Discos Rígidos (HDDs)
# Carga de trabalho: Mista (arquivos grandes e pequenos, típico de ML/HPC)
# Foco: Maximizar throughput e garantir latência consistente.

[main]
# Descrição amigável do perfil, visível com 'tuned-adm list'.
summary=BeeGFS Storage em HDD (workload misto: grandes + pequenos arquivos ML)

# Herda todas as configurações do perfil 'throughput-performance' como base.
# As configurações abaixo irão sobrescrever ou adicionar novas regras.
include=throughput-performance

[sysctl]
# ---- Rede ----
# Otimizações para redes de alta velocidade (10GbE+) e alto volume de conexões.

# Define o buffer máximo de recebimento de socket (256 MiB) para evitar perda de pacotes em redes de alta velocidade.
net.core.rmem_max=268435456
# Define o buffer máximo de envio de socket (256 MiB) para otimizar a transmissão de grandes volumes de dados.
net.core.wmem_max=268435456
# Aumenta a fila de pacotes recebidos antes do processamento pelo kernel para lidar com rajadas de tráfego.
net.core.netdev_max_backlog=250000
# Define os buffers de recebimento TCP (min, default, max), permitindo que conexões usem até 256 MiB.
net.ipv4.tcp_rmem=4096 87380 268435456
# Define os buffers de envio TCP (min, default, max), permitindo que conexões usem até 256 MiB.
net.ipv4.tcp_wmem=4096 65536 268435456
# Habilita a descoberta automática do MTU ideal no caminho de rede para evitar fragmentação de pacotes.
net.ipv4.tcp_mtu_probing=1
# Altera o algoritmo de controle de congestionamento para HTCP, mais agressivo e ideal para redes de alta performance.
net.ipv4.tcp_congestion_control=htcp
# Aumenta a fila de conexões pendentes para lidar com um número massivo de clientes simultâneos.
net.core.somaxconn=65535
# Aumenta a memória para dados auxiliares de sockets, suportando operações de rede intensivas.
net.core.optmem_max=25165824

# ---- Memória ----
# Otimizações para manter dados na RAM e evitar pausas de I/O.

# Reduz drasticamente o uso da partição swap (valor 1 de 100), forçando o sistema a manter os dados na RAM (muito mais rápida).
vm.swappiness=1
# Define que processos que geram dados são forçados a escrever no disco quando 10% da memória está "suja".
vm.dirty_ratio=10
# Inicia a escrita de dados "sujos" em segundo plano quando 5% da memória está ocupada, evitando "I/O storms" (longas pausas de I/O).
vm.dirty_background_ratio=5
# Força o kernel a manter um mínimo de 256 MiB de RAM livre para estabilidade sob carga pesada.
vm.min_free_kbytes=262144

# ---- HDDs: workload misto ----
# Otimizações específicas para o subsistema de I/O com discos mecânicos.

# Define o escalonador de I/O para 'mq-deadline', ideal para HDDs por minimizar o movimento das cabeças e dar previsibilidade.
block/sd*/queue/scheduler=mq-deadline
# Aumenta a profundidade da fila de I/O, permitindo que o escalonador otimize mais requisições simultaneamente.
block/sd*/queue/nr_requests=256
# Configura a leitura adiantada (read-ahead) para 512 KB, acelerando a leitura de arquivos sequenciais.
block/sd*/queue/read_ahead_kb=512

[bootloader]
# ATENÇÃO: As alterações nesta seção exigem uma REINICIALIZAÇÃO para serem aplicadas.

# Adiciona os seguintes parâmetros na linha de comando de inicialização do kernel:
# - transparent_hugepage=never: Desabilita Huge Pages para evitar picos de latência e garantir performance consistente.
# - intel_idle.max_cstate=1 / processor.max_cstate=1: Desabilita estados profundos de economia de energia da CPU para minimizar a latência de resposta.
cmdline=transparent_hugepage=never intel_idle.max_cstate=1 processor.max_cstate=1
```

---

### 2.2 Pontos-chave do tuning

* **Rede**: buffers grandes, congestion control `htcp`, backlog alto.
* **Memória**: baixo uso de swap, flush de dirty pages mais agressivo.
* **Discos (HDD)**:

  * `mq-deadline` → melhor para fairness em discos mecânicos.
  * `nr_requests=256` → fila moderada, evita sobrecarga.
  * `read_ahead_kb=512` → equilíbrio entre arquivos grandes e pequenos.
* **Boot params**:

  * `transparent_hugepage=never` → evita jitter.
  * `intel_idle.max_cstate=1` e `processor.max_cstate=1` → reduz latência de wake-up da CPU.

---

## 3. Checklist de Validação

1. Ativar serviço e perfil:

   ```bash
   systemctl enable --now tuned
   tuned-adm profile beegfs-storage-hdd-mixed
   tuned-adm active
   ```

2. Conferir discos:

   ```bash
   cat /sys/block/sd*/queue/scheduler
   cat /sys/block/sd*/queue/nr_requests
   cat /sys/block/sd*/queue/read_ahead_kb
   ```

3. Conferir rede:

   ```bash
   sysctl net.core.rmem_max
   sysctl net.core.wmem_max
   sysctl net.ipv4.tcp_congestion_control
   ```

4. Conferir memória:

   ```bash
   sysctl vm.swappiness
   sysctl vm.dirty_ratio
   sysctl vm.dirty_background_ratio
   ```

5. Conferir boot params:

   ```bash
   cat /proc/cmdline
   ```

---

## 4. Plano de Testes com **IOR 4.0.0 + mpirun**

### 4.1 Ambiente

* **IOR 4.0.0** compilado com MPI.
* Executar em pelo menos 2 nós clientes acessando o BeeGFS-storage.
* Diretório de teste: `/mnt/beegfs/test/`.

### 4.2 Comandos de benchmark

🔹 Arquivos grandes (streaming sequencial, 1 MB block, 16 MB transfer):

```bash
mpirun -np 8 numactl --cpunodebind=0 --membind=0 \
  ior -w -r -o /mnt/beegfs/test/bigfile \
      -t 1m -b 16m -F -k
```

🔹 Arquivos pequenos (4 KB blocos, simulação de ML dataset):

```bash
mpirun -np 8 numactl --cpunodebind=0 --membind=0 \
  ior -w -r -o /mnt/beegfs/test/smallfiles \
      -t 4k -b 64k -F -k
```

🔹 Workload misto (128 KB blocos, equilíbrio):

```bash
mpirun -np 8 numactl --cpunodebind=0 --membind=0 \
  ior -w -r -o /mnt/beegfs/test/mixed \
      -t 128k -b 4m -F -k
```

* `-F` → cada processo escreve seu próprio arquivo.
* `-k` → manter os arquivos após o teste (para inspeção).

---

## 5. Plano de Ação – Implantação controlada

1. **Ambiente de Teste (PoC)**

   * Escolher 1 servidor BeeGFS-storage com HDD.
   * Ativar perfil `beegfs-storage-hdd-mixed`.
   * Rodar os benchmarks IOR acima.
   * Registrar métricas (IOPS, throughput, latência).

2. **Comparação com baseline**

   * Reverter para `virtual-guest` ou `throughput-performance`.
   * Rodar os mesmos testes IOR.
   * Comparar os resultados.

3. **Validação com workload real**

   * Rodar aplicações de ML/DL reais (treino leve com TensorFlow/PyTorch) usando BeeGFS.
   * Verificar impacto em latência e throughput.

4. **Escalonar**

   * Se os ganhos forem consistentes, aplicar o perfil em todos os storage targets HDD.
   * Manter monitoramento ativo (`beegfs-ctl --getentryinfo`, `beegfs-ctl --storagepools`) e métricas de I/O.

---

# 🎯 Conclusão

* O perfil `beegfs-storage-hdd-mixed` traz equilíbrio entre grandes arquivos (streaming) e pequenos arquivos (ML).
* Testes com **IOR 4.0.0 + mpirun** garantem validação objetiva antes da produção.
* A implantação deve seguir **PoC → Comparação → Workload real → Escalonamento**.

---
