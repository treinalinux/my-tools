#!/bin/bash
# Alan Alves
# 11/08/2025
#
# ===================================================================
# SCRIPT FINAL (v10) - CRIA ISO MINIMAL DO FEDORA COM DRIVER
# ===================================================================

# Para o script se qualquer comando falhar
set -e

# --- CONFIGURAÇÃO ---
# Altere o IP se a sua máquina servidora mudar de endereço
IP_SERVIDOR="192.168.0.154"
# --------------------

echo "--- ETAPA 1: LIMPANDO TUDO ---"
#cd /home/fieldiag
#rm -rf custom-iso final-iso-source minha_nova_iso_minima
rm -rf custom-iso final-iso-source
rm -vf Fedora-FIELDIAG-minimal.iso temp.iso
echo "Ambiente limpo."
echo ""

echo "--- ETAPA 2: CRIANDO O SISTEMA DE ARQUIVOS BASE (MÍNIMO) ---"
# mkdir -vp /home/fieldiag/minha_nova_iso_minima
dnf --installroot=/home/fieldiag/minha_nova_iso_minima --releasever=41 --use-host-config install @core @development-tools kernel kernel-devel wget shim-x64 grub2-efi-x64 dracut-live tar -y
# dnf --installroot=/home/fieldiag/minha_nova_iso_minima --releasever=41 --use-host-config install @core @development-tools kernel kernel-devel wget shim-x64 grub2-efi-x64 dracut-live tar tcpdump nmap htop lshw lspci hwinfo inxi dmidecode usbutils pciutils curl iotop smartmontools hdparm partx vmstat glxinfo lm_sensors collectl glances nload iptraf sysstat nmon vim neovim nfs-utils python3 ddrescue lvm xfsprogs libibverbs rdma-core opensm gcc gcc-c++ libgfortran openmpi openmpi-devel mpich mpich-devel openblas-devel lapack-devel slurm ansible.noarch vim-ansible.noarch glibc-langpack-pt sos
echo "Sistema de arquivos base criado."
echo ""

echo "--- ETAPA 3: CUSTOMIZANDO O SISTEMA (CHROOT) ---"
mount --bind /proc /home/fieldiag/minha_nova_iso_minima/proc
mount --bind /dev /home/fieldiag/minha_nova_iso_minima/dev
mount --bind /sys /home/fieldiag/minha_nova_iso_minima/sys

# Executa os comandos de customização dentro do chroot
chroot /home/fieldiag/minha_nova_iso_minima /bin/bash -c "
  set -e
  export PATH=\$PATH:/usr/sbin:/sbin
  echo 'Baixando FIELDIAG.tar...'
  wget http://$IP_SERVIDOR:8000/FIELDIAG.tar -O /root/FIELDIAG.tar
  echo 'Extraindo FIELDIAG.tar...'
  tar -xvf /root/FIELDIAG.tar -C /root/
  echo 'Extraindo driver.tgz...'
  tar -xzvf /root/driver.tgz -C /root/
  INSTALLED_KERNEL=\$(rpm -q kernel --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort -V | tail -n 1)
  echo 'Kernel a ser usado: \$INSTALLED_KERNEL'
  cd /root/driver
  echo 'Compilando o módulo...'
  make -C /lib/modules/\$INSTALLED_KERNEL/build M=\$(pwd) modules
  echo 'Instalando o módulo...'
  mkdir -p /lib/modules/\$INSTALLED_KERNEL/updates/
  cp mods.ko /lib/modules/\$INSTALLED_KERNEL/updates/
  depmod -a \$INSTALLED_KERNEL
  echo 'Blacklist do driver Nouveau...'
  echo 'blacklist nouveau' > /etc/modprobe.d/blacklist-nouveau.conf
  echo 'Reconstruindo initramfs com módulos live...'
  dracut --force --add dmsquash-live /boot/initramfs-\${INSTALLED_KERNEL}.img \${INSTALLED_KERNEL}
  rm /etc/resolv.conf
  echo 'nameserver 8.8.8.8' > /etc/resolv.conf
  dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
  dnf install -y https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
  dnf install nvidia-smi glibc-langpack-pt -y
  echo 'Limpando arquivos de instalação...'
  rm -rf /root/FIELDIAG.tar /root/driver.tgz /root/driver /root/fieldiag /root/install_module.sh /root/NV_Field_Diag_Software.pdf
"

# Desmonta o chroot
umount /home/fieldiag/minha_nova_iso_minima/proc
umount /home/fieldiag/minha_nova_iso_minima/dev
umount /home/fieldiag/minha_nova_iso_minima/sys
echo "Customização concluída."
echo ""

echo "--- ETAPA 4: EMPACOTANDO A ISO FINAL ---"
#cd /home/fieldiag
mkdir -vp custom-iso/LiveOS custom-iso/EFI/BOOT custom-iso/isolinux

echo "Criando squashfs.img..."
mksquashfs /home/fieldiag/minha_nova_iso_minima/ custom-iso/LiveOS/squashfs.img -noappend -comp xz

echo "Copiando arquivos de boot..."
KERNEL_FILE=$(ls -t /home/fieldiag/minha_nova_iso_minima/boot/vmlinuz-* | tail -n 1)
echo ${KERNEL_FILE}
INITRAMFS_FILE=$(ls -t /home/fieldiag/minha_nova_iso_minima/boot/initramfs-*.img | head -n 1)
echo ${INITRAMFS_FILE}
cp -v "$KERNEL_FILE" custom-iso/isolinux/vmlinuz0
cp -v "$INITRAMFS_FILE" custom-iso/isolinux/initrd0.img
cp -v /usr/share/syslinux/*.c32 custom-iso/isolinux/
cp -v /usr/share/syslinux/isolinux.bin custom-iso/isolinux/
cp -v /home/fieldiag/minha_nova_iso_minima/boot/efi/EFI/fedora/shimx64.efi custom-iso/EFI/BOOT/BOOTX64.EFI
cp -v /home/fieldiag/minha_nova_iso_minima/boot/efi/EFI/fedora/grubx64.efi custom-iso/EFI/BOOT/

echo "Criando arquivos de configuração de boot..."
cat > custom-iso/isolinux/isolinux.cfg << EOF
UI menu.c32
MENU TITLE Fedora-FIELDIAG Minimal
TIMEOUT 100
LABEL start
  MENU LABEL Start Fedora-FIELDIAG (Minimal)
  KERNEL vmlinuz0
  APPEND initrd=initrd0.img rd.live.image rd.live.label=Fedora-FIELDIAG quiet
  MENU DEFAULT
EOF

cat > custom-iso/EFI/BOOT/grub.cfg << EOF
set timeout=10
menuentry 'Start Fedora-FIELDIAG (Minimal)' {
    linuxefi /isolinux/vmlinuz0 rd.live.image rd.live.label=Fedora-FIELDIAG quiet
    initrdefi /isolinux/initrd0.img
}
EOF

echo "Criando a ISO final..."
xorriso -as mkisofs \
    -o Fedora-FIELDIAG-minimal.iso \
    -V "Fedora-FIELDIAG" \
    -J -r \
    -isohybrid-mbr /usr/share/syslinux/isohdpfx.bin \
    -c isolinux/boot.cat \
    -b isolinux/isolinux.bin \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    -eltorito-alt-boot \
    -e EFI/BOOT/BOOTX64.EFI \
    -no-emul-boot -isohybrid-gpt-basdat \
    custom-iso/

echo ""
echo "--- PROCESSO CONCLUÍDO! ---"
echo "Arquivo Fedora-FIELDIAG-minimal.iso está pronto em /home/fieldiag."
