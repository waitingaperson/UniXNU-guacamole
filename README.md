# UniXNU-guacamole

Bring-up repository for running the `ios-sweet` guacamole XNU and the iPhone X
iOS 16.7.16 userland on a OnePlus 7 Pro (guacamole, SM8150) through Project
Aloha UEFI and UniXNU/DarwinBoot.

`ios-sweet` remains the kernel/rootfs source. This repository owns the UEFI
integration, the `GUACESP` payload, the Android boot image, and the board file.

## Status

Hardware-verified on a GM1910 with `fastboot boot` (no partition was written):

- The rebuilt NOSB firmware starts and the UniXNU menu lists
  **"OnePlus 7 Pro - XNU"**.
- UniXNU mounts the 64 MiB `GUACESP` FAT32 payload, reads
  `\EFI\UniXNU\unixnu.toml`, and passes it to DarwinBoot.
- DarwinBoot reads `Payloads/kernel.macho` plus `.adt`, validates them, prints
  `DARWINBOOT: inputs validated; exiting boot services`, then hands off.
- r14 fixes the handoff window: DarwinBoot aligns the physical base to the
  kernel's 32 MiB bootstrap L2 block (16 KiB XNU build). Hardware confirms
  this reaches XNU; the first r14 boot panicked in `arm_vm_init`'s early I/O
  page-table reservation, not at kernel entry.
- `boot-32-r15.img` requests a 3 GiB `/chosen/darwinboot-memory-size`, which
  reserves enough early I/O page tables for the 36 MiB framebuffer.
- **Hardware-verified:** r15 reaches the iOS userland on the panel.

The GPU/GMU bring-up is a kernel-side blocker and is tracked in `ios-sweet`.

## Kernel build (branch `kernel-8796`)

The `kernel-8796` branch replaces the copied ios-sweet kernel with a UniXNU
build of `xnu-8796.141.3`:

- 4 KiB `BCM2837` machine config, `ArmDTPlatform`, `ArmCpu`, source
  corecrypto and libpthread 514;
- device-specific `feeds.toml`, `unixnu.lock`, `configs/guacamole_8796_defconfig`
  and a 24-patch `patches/xnu/` series;
- macOS workflow `kernel-8796` builds and seals
  `out/guacamole/kernel/kernel-8796.macho`.

The kernel currently builds, but storage/display drivers and
`[kernel.prelink]` are still to be ported. The r15 16 KiB chain remains the
known-good fallback.

## Layout

```
board.toml                 UniXNU board file (firmware/payload/bootimg)
scripts/                   build wrappers, ADT tools, guacamole device profile
patches/                   changes required in the external UniXNU/UEFI trees
uefi/                      Project Aloha Mu-Silicium tree (ignored)
unixnu/                    UniXNU build driver and EFI packages (ignored)
reference/UniXNU-sheng/    sheng device repo, integration reference (ignored)
inputs/                    kernel Mach-O, ADTs, DTB, prebuilt FV (ignored)
out/                       build products (ignored)
```

## External trees

The build needs two checkouts next to this repository:

```sh
git clone https://github.com/UniXNU/UniXNU unixnu
git clone --recurse-submodules https://github.com/Project-Aloha/mu_aloha_platforms uefi

git -C unixnu checkout b6ae99c
git -C uefi checkout 0b798128

git -C unixnu apply ../patches/unixnu-guacamole.patch
git -C unixnu/drivers/DarwinBoot apply ../../../patches/darwinboot-guacamole.patch
git -C uefi apply ../patches/aloha-guacamole.patch
```

`patches/unixnu-guacamole.patch` carries the config-volume diagnostics, the
volume-root path fix, the Aloha shim header check, and the firmware define
formatting. `patches/darwinboot-guacamole.patch` makes the kernel window
congruent with the 16 KiB XNU kernel's 32 MiB bootstrap L2 blocks.
`patches/aloha-guacamole.patch` carries the DTB-preserving BootShim,
`ShengBootMemoryDxe`, the UniXNU/DarwinBoot INFs, and the guacamole
boot-image resources.

## Build inputs

The kernel and base ADT are built in `ios-sweet`:

- `xnu/out-guacamole/kernel.development.guacamole`
- `shim/out/guacamole.adt`
- `research/ipsw-x/d22ap.adt`

The iOS rootfs stays on the phone. The D22AP base ADT is an Apple artifact and
is kept out of git; `scripts/make-guacamole-adt.py` needs it as
`scripts/base-d22ap.adt` (or `inputs/`). Place the kernel at
`inputs/guacamole/kernel.macho`, the Aloha DTB at
`inputs/uefi-prebuilt/guacamole.dtb`, and the prebuilt FV at
`inputs/uefi-prebuilt/nosb_fv.fd`.

## Build

```sh
python3 scripts/build-firmware.py
python3 scripts/build-payload.py
python3 scripts/build-bootimg.py \
  --fd uefi/Build/SurfaceDuo1Pkg/DEBUG_CLANGPDB/FV/SM8150_EFI.fd \
  --dtb inputs/uefi-prebuilt/guacamole.dtb \
  -o out/guacamole/boot/boot-32-r15.img
```

The payload is a 64 MiB FAT32 image. 32 MiB is not enough: it yields 64,496
clusters, below the FAT32 minimum of 65,525, and EDK2 `FatDxe` refuses to
mount it even though the boot-sector check passes.

`scripts/build-bootimg.py` packs the full 2,779,551-byte Aloha DTB table and
patches `linux,initrd-start/-end` in only its first FDT. The ABL relocates the
payload and rewrites those properties on the live DTB; `ShengBootMemoryDxe`
publishes the resulting `GUACESP` volume.

## Test

```sh
fastboot boot out/guacamole/boot/boot-32-r15-retest.img
```

The `kernel-8796` branch carries a from-source XNU 8796 rebuild. The verified
userspace image is the r15 reproduction (`boot-32-r15-retest.img`, ios-sweet
`kernel.development.guacamole`, sha256 `f9080dac...`), which reaches the iOS
userland on hardware. The from-source kernel currently stops in `setconf`
(UFS DMA allocation); the prelink route is ruled out for this kernel and the
next step is porting the ios-sweet monolithic patch set (100 of 102 patches
apply cleanly to a fresh 8796 tree).

`fastboot boot` is temporary and leaves Android and every partition untouched.
Use the NOSB image only; secure-boot builds cannot load the unsigned
UniXNU/DarwinBoot drivers.

## References

- `NOTES.md` - hardware evidence, failed attempts, and the active handoff.
- [UniXNU](https://github.com/UniXNU/UniXNU) and
  [UniXNU-sheng](https://github.com/UniXNU/UniXNU-sheng) for the boot chain.
- [Project Aloha](https://github.com/Project-Aloha/mu_aloha_platforms) for the
  guacamole UEFI tree.
