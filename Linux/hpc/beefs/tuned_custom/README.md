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
[main]
summary=BeeGFS Storage em HDD (workload misto: grandes + pequenos arquivos ML)
include=throughput-performance

[sysctl]
# ---- Rede ----
net.core.rmem_max=268435456
net.core.wmem_max=268435456
net.core.netdev_max_backlog=250000
net.ipv4.tcp_rmem=4096 87380 268435456
net.ipv4.tcp_wmem=4096 65536 268435456
net.ipv4.tcp_mtu_probing=1
net.ipv4.tcp_congestion_control=htcp
net.core.somaxconn=65535
net.core.optmem_max=25165824

# ---- Memória ----
vm.swappiness=1
vm.dirty_ratio=10
vm.dirty_background_ratio=5
vm.min_free_kbytes=262144

# ---- HDDs: workload misto ----
block/sd*/queue/scheduler=mq-deadline
block/sd*/queue/nr_requests=256
block/sd*/queue/read_ahead_kb=512

[bootloader]
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
