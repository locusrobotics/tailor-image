#! /bin/bash

name=$1
distro=$2

# Make a 2048M disk
dd if=/dev/zero of=$name.raw bs=1024 count=1 seek=2048000

# Partition
parted -s $name.raw -- mklabel msdos mkpart primary 1m 2048m toggle 1 boot

# Setup loopback debice
loopback=$(losetup --show -f $name.raw)
partprobe $loopback
echo "Created $loopback"

# Mount first partition to /mnt
mkfs -O ^metadata_csum -t ext4 "$loopback"p1
mount "$loopback"p1 /mnt

# Create image
# TODO(gservin): Wanted to use minibase, but at least on xenial it pulls sysvinit
debootstrap --include=linux-image-generic $distro /mnt

# Cleanup
echo "Cleanup"
umount /mnt
losetup -d $loopback
echo "Done"

echo "Converting to qcow2"
qemu-img convert -f raw -O qcow2 $name.raw $name
rm -f $name.raw
