# UniXNU-guacamole notes

## Active status (2026-10-22)

- **Full chain verified on hardware (2026-10-22).** r15 boots through
  UniXNU -> DarwinBoot -> XNU -> iOS. The user confirmed the iOS userland on
  the panel. No partition was written; every test used `fastboot boot`.
- **r14 32 MiB alignment fix verified.** The first r14 boot panicked in the
  kernel, which proves the kernel entry and `start.s` mapping now work:
  ```
  SWEET EARLY PANIC: pmap_map_bd_with_options: no PIE for
  vaddr=0xfffffe000c000000, virt=0xfffffe000a000000,
  start=0x9c000000, end=0x9e400000, prot=0x3, options=0x1 @pmap.c:1035
  ```
  - DarwinBoot had allocated the window at `2 MiB boundary +
    (Kernel.Base & 0x1fffff)`. The 16 KiB kernel's bootstrap KVA mapping uses
    32 MiB L2 blocks, so `PhysicalBase` must be congruent modulo **32 MiB**;
    the old layout put the first post-MMU fetch 16 MiB off.
  - `AllocateWindow` now uses
    `ALIGN_VALUE(PhysicalStart, SIZE_32MB) + (Kernel.Base & (SIZE_32MB - 1))`.
    Host simulation: old VA->PA `+0x1000000`, new `+0`. The rebuilt
    `DarwinBoot.efi` disassembles with `and x11, x11, #0x1ffffff`.
- **r15 fixes the panic: 3 GiB DarwinBoot window.** The panic is the
  framebuffer `io_map` crossing an unmapped L3 boundary, not a bad PTE at the
  first address. `arm_vm_init` reserves early I/O page tables for
  `2 MiB + 10 MiB per 256 MiB of memSize + framebuffer size`. With the
  default 256 MiB window that is only ~48 MiB; startup allocations push
  `virtual_space_start` to `0xfffffe000a000000`, and the 0x2400000-byte
  framebuffer then needs page tables past `0xfffffe000c000000`, where none
  were reserved.
  - `[payload.adt] owned_memory_size = "0xc0000000"` now emits
    `/chosen/darwinboot-memory-size = 0xc0000000` (12 segments, ~158 MiB
    reservation), matching the working shim's 3 GiB `memSize`.
  - `mkadt.py` validates 256 MiB - 8 GiB in 2 MiB steps and exposes
    `--owned-memory-size`; `make-guacamole-adt.py` forwards it.
  - ADT dump confirms `darwinboot-memory-size = 0xc0000000`.
- **r15 image verified:** `out/guacamole/boot/boot-32-r15.img`
  (72,302,592 bytes, sha256 `ff672bce...`), FV `7bc92c83...`, payload
  `f74da572...`. It reaches iOS on hardware.
- Local UniXNU, DarwinBoot and Aloha changes are exported as
  `patches/*.patch`; the external trees remain ignored.

## 2026-10-22: UniXNU-built xnu-8796 kernel (branch `kernel-8796`)

- **The kernel now builds with UniXNU's method, not from the ios-sweet blob.**
  `xnu-8796.141.3` (the last open-source tag matching the iPhone X 16.7.16
  generation) is built as a 4 KiB `BCM2837` kernel with
  `ArmDTPlatform` + `ArmCpu`, source corecrypto, and a real libpthread
  component. CI run `39702265755`, job `119574041206`.
- The kernel is `out/guacamole/kernel/kernel-8796.macho`, 15,228,600 bytes,
  sha256 `8a941583...`. It is linked and crypto-sealed; `unixnu` stops only at
  `board.toml has no [kernel.prelink]`, which is deliberate for this milestone.
- Build inputs are pinned in `feeds.toml`/`unixnu.lock`: XNU
  `1b191cb` (`xnu-8796.141.3`), libpthread `a6c70ca`
  (`libpthread-514.100.2`), libplatform/libdispatch/AvailabilityVersions as
  listed, and corecrypto-2023 `11fba65`.
- `configs/guacamole_8796_defconfig` is the first-stage config: no storage,
  display or GPU. `patches/xnu` is a 24-patch 8796 series; 19 were taken from
  UniXNU after `git apply --check`, and the rest are the 8796-specific fixes:
  rebased `source-machine-layer` and `apple-only-cpu-tunables`, the kpc stub,
  `CFLAGS_EXTRA`, clang `-MJ` compile records, iOS 16 deployment, and the
  libpthread 514 builder.
- **Prelink now works against the iPhone X kernelcache.** With
  `out/ipsw/kernelcache.arm64` (sha256 `2ec297...`) and roots
  `AppleARMPlatform`, `AppleARMWatchdogTimer`, `hfs.kext`,
  `IOHIDFamily`, `IOReportFamily`, `IOStorageFamily`, the native kernel
  prelinks to `unixnu/out/guacamole/kernel/kernel.macho` (51 MiB,
  sha256 `710522bc...`). The planner resolves AMFI, PMGR, CoreTrust,
  AppleImage4, corecrypto, HFS, storage and HID dependencies.
  `slide=-0x1000000`, matching the sheng-qualified kernelcache base.
- **SM8150 UFS port compiles in the 4K kernel.** `patches/xnu/0400-guacamole-ufs-root.patch` adds the proven ios-sweet `bsd/dev/sweet_ufs.c` driver and routes `rd=ufsroot0` to it from `IOKitBSDInit`. It reads `/sweet-ufs` from the ADT and exposes the `userdata` GPT partition as `ufsroot0`. CI run `39707207800` built and sealed it without errors. The UFS kernel is 15,246,152 bytes, sha256 `0f031930...`; the prelinked image is 53,133,312 bytes, sha256 `b7a2f223...`. The next boot test will use it.
- **NativeUfs is not portable as-is.** It matches
  `qcom,sm8550-ufshc` and uses sheng's GCC/UFS windows, so it cannot bind
  guacamole's SM8150 controller. The ios-sweet UFS driver is the current
  SM8150 reference; either port it to the 4K kernel or extend NativeUfs with
  guacamole's GCC/UFS/SMMU addresses. The display side has the same issue:
  sheng's Legacy display builder is A740/sheng-specific.
- **r16 4 KiB boot failed.** `boot-32-r16.img` (72,302,592 bytes, sha256
  `c875f989...`) contains the 4 KiB kernel (`ea6cd866...`) with UFS and the
  built-in AppleCLCD/SweetSurface framebuffer, prelinked to
  `7b133ea8...` (53,202,944 bytes). After `fastboot boot`, the fastboot
  device disappeared at 10:04:10 and a `05c6:900e QUSB_BULK_SN` Qualcomm
  device appeared at 10:04:34; no UEFI gadget or display output was seen.
  The phone had to be recovered manually. This is an early crash/reset, not
  a UFS/HFS result. The next test must add an early framebuffer/panic
  console (or boot a minimal 4K kernel without UFS/framebuffer) to separate
  kernel entry/prelink from the new drivers.
- The previous 16 KiB r15 chain remains the known-good boot path. The 4 KiB
  kernel is built and prelinked; storage and display compiled, but the first
  boot attempt did not reach a visible stage.

## 2026-10-21: project split

- The UEFI/UniXNU bring-up is now a separate project (`UniXNU-guacamole`).
  `ios-sweet` is unchanged except as the source of the kernel, ADT, base ADT
  and the iOS root on the phone.
- `uefi/` is the Project Aloha Mu-Silicium tree used by the prebuilt
  `oneplus-guacamole_NOSB.img` (773 MB, `.git` included). Its submodules were
  not checked out in `/tmp`; they are being initialized here.
- `unixnu/` is the UniXNU build driver and EFI packages. `drivers/DarwinBoot`
  is a submodule. `reference/UniXNU-sheng` is the sheng device repo; it shows
  the working layout (`loader = "firmware"`, FAT payload ramdisk, DarwinBoot
  in the FV).

## Current build state (2026-10-22)

- `scripts/build-payload.py` produces a **64 MiB** FAT32 payload
  (`out/guacamole/payload/payload.img`) with `EFI/UniXNU/unixnu.toml`, the
  17,206,448-byte guacamole kernel Mach-O, and the 12,636-byte ADT. The
  wrapper runs `mkadt.py --device guacamole --dram-size 0xc0000000
  --owned-memory-size 0xc0000000`.
  64 MiB is the minimum that yields a legal FAT32 cluster count (129,022;
  the earlier 32 MiB image had 64,496, below the 65,525 limit, and EDK2
  `FatDxe` refused to mount it).
- `scripts/build-bootimg.py` packs `out/guacamole/boot/boot-32-r15.img`
  (72,302,592 bytes, sha256 `ff672bce...`, payload `f74da572...`) with the
  rebuilt FV (`7bc92c83...`), the full 2,779,551-byte Aloha DTB table, and patched
  first-FDT `/chosen/linux,initrd-start/-end` at `0x836ff000`-relative
  values. The ABL relocates the payload and rewrites the properties on the
  live DTB; `ShengBootMemoryDxe` validates the `GUACESP` boot sector and
  publishes the block device. The earlier r13 image is the one that first
  showed the menu.
- The appended DTB is not one FDT: the first blob's total-size field is
  `0x7bed2`. `build-bootimg.py` patches only that blob and preserves the
  rest byte for byte.
- The prebuilt-FV image has no `UniXNUDxe`/`UniXNU`/`DarwinBoot`; only the
  rebuilt `SM8150_EFI.fd` shows the menu.
- `scripts/build-firmware.py` drives the Aloha NOSB build. The local tree
  needs the patches in `patches/aloha-guacamole.patch` (BootShim DTB save,
  ShengBootMemoryDxe, UniXNU/DarwinBoot INFs, FDT/UniXNU libraries).

## Verified on the phone

- `fastboot boot out/guacamole/boot/boot-32-r13.img` starts the rebuilt
  firmware; the UniXNU menu lists **"OnePlus 7 Pro - XNU"**, proving the
  FAT32 payload, `GUACESP` volume, config read, and `unixnu.toml` parse.
- Selecting the entry reaches DarwinBoot:
  `DARWINBOOT: inputs validated; exiting boot services`; the panel then stops
  there. The earlier bootloader blockers are all resolved.
- The Aloha guacamole FDF includes UFSDxe, FAT, PartitionDxe,
  RamPartitionDxe, SimpleFbDxe, BdsDxe. `DisplayDxe` is commented out.
- No partition was written; every test used `fastboot boot`.

## Existing guacamole kernel/ADT

- Kernel: `../ios-sweet/ios-sweet/xnu/out-guacamole/kernel.development.guacamole`
  (17,206,448 bytes), linked with the guacamole board code.
- ADT: `shim/out/guacamole.adt` (0x3130 bytes), generated by
  `tools/mkadt.py --device guacamole --dram-size 0xc0000000`.
- The ADT identifies as iPhone10,3 / D22AP, `oneplus,guacamole`,
  `qcom,sm8150`; `unique-chip-id` is the synthetic `0x5357454554000001`.
- The current shim payload (0087) command line is:
  `debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress
  rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1
  wdt_test=no_user_checkin ufsrw=1 rootrw=1 launchd_unsecure_cache=1
  wdt=-1 sweetusb=0 sweettouchdelay=20 sweetfb_noconsole=1 sweetfb_hz=30
  sweetgpu=3 sweetlogdump=1`
- The iOS userland is iPhone X 16.7.16 (20H392) on the phone's UFS; it is not
  copied into this project.

## UniXNU integration facts

- `unixnu build payload` writes a FAT image with:
  - `EFI/UniXNU/unixnu.toml`
  - `EFI/UniXNU/Payloads/kernel.macho`
  - `EFI/UniXNU/Payloads/kernel.macho.adt`
  - optional `kernel.macho.trustcache`, `scratch-data.img`
- `loader = "firmware"` means DarwinBoot is in the UEFI FV and no
  `[[driver]]` entry is written. The FAT is the boot image ramdisk.
- The ADT tool is called with `--output`, `--dram-size` and the generic ADT
  flags. `scripts/make-guacamole-adt.py` accepts those and calls the copied
  `mkadt.py` with `--device guacamole`; the guacamole profile owns the values.
- The kernel ADT path is not the same as the sheng iPad ADT: this port uses the
  iPhone X D22AP identity because the installed userland is iPhone X 16.7.16.
- `unixnu bootimg` compiles the Aloha `BootShim/BootShim.S` with
  `FD_BASE`/`FD_SIZE`; the Aloha source uses `UEFI_BASE`/`UEFI_SIZE`, so the
  file now aliases them. The local `bootimg.py` header check was relaxed to
  accept the Aloha shim (`_StackSize` is the FV size, not shim+FV).

## Firmware integration (done)

1. Build the Aloha NOSB FV with the UniXNU/DarwinBoot INFs (see
   `patches/aloha-guacamole.patch` for the exact DSC/FDF changes).
2. `ShengBootMemoryDxe` publishes the `GUACESP` FAT from the DTB initrd range
   or, as a fallback, by scanning the UEFI memory map for the boot sector.
3. `UniXNUDxe`/`UniXNU` load `\EFI\UniXNU\unixnu.toml` from that volume.
4. `DarwinBoot` reads `Payloads/kernel.macho` and `.adt`, builds
   `DARWIN_BOOT_ARGS`, exits boot services, and jumps to XNU at EL1.

## Open blockers

- **DarwinBoot -> XNU handoff.** DarwinBoot validates the kernel/ADT and exits
  boot services, but XNU produces no early framebuffer output. The leading
  cause is the 2 MiB window alignment described in the active status; the
  fix is not yet applied or tested.
- GPU/GMU: the ARC/RSCC/CM3 chain is still blocked in the kernel. The
  bootloader change does not address it. See `ios-sweet` NOTES for the
  latest GMU/RSCC evidence.
- Secure Boot: use the NOSB image for unsigned UniXNU/DarwinBoot. Never the
  SB variant.
- No `.ipsw` URL is stored here; the IPSW/root is an external input. The
  payload path does not fetch it.

## Local commands

```sh
# apply the framework patches to the external trees
git -C unixnu apply ../patches/unixnu-guacamole.patch
git -C unixnu/drivers/DarwinBoot apply ../../../patches/darwinboot-guacamole.patch
git -C uefi apply ../patches/aloha-guacamole.patch

# build (external inputs under inputs/)
python3 scripts/build-firmware.py
python3 scripts/build-payload.py
python3 scripts/build-bootimg.py \
  --fd uefi/Build/SurfaceDuo1Pkg/DEBUG_CLANGPDB/FV/SM8150_EFI.fd \
  --dtb inputs/uefi-prebuilt/guacamole.dtb \
  -o out/guacamole/boot/boot-32-r15.img

# flash-free test
fastboot boot out/guacamole/boot/boot-32-r15.img
```

Fastboot is only valid while the phone is in the bootloader. The UEFI USB
gadget is not usable for control.

## 2026-10-22: the iPhone X 16.7.16 kernelcache cannot prelink this kernel

- Extracted `kernelcache.release.iphone10b` from the iPhone X 16.7.16 IPSW
  (18,204,358 bytes IM4P/LZFSE -> 50,937,884-byte arm64 Mach-O). Its kernel is
  `Darwin Kernel Version 22.6.0 ... xnu-8796.142.1.703.8~1`.
- The ios-sweet kernel (`xnu/out-guacamole/kernel.development.guacamole`,
  sha256 `f9080dac...`) is `xnu-8796.141.3`. `NativePrelink.plan` stops at
  `Kernel target 0xfffffff00734c520 has 0 native address candidates:
  ['_vfs_getvfs_with_vfsops']`; the native kernel also lacks the UniXNU
  `_kalloc_sparse_prelink_index_version` and
  `_native_prelink_security_init_version` exports. Do not force the prelink.
- The shipping kernel is monolithic: the last boot log registers `SWEET HFS`
  and `SWEET AMFI`, and mounts the root as HFS
  (`/dev/ufsroot0 on / (hfs, local, journaled, noatime)`). It does not load a
  kext kernelcache, so the iPhone X kernelcache is not needed for this boot
  chain. DarwinBoot maps `[Kernel.Base, Kernel.End]` as one window; a prelink
  would also have to put every kext in the kernel's reserved low hole.
- Current images already use the raw kernel: `out/guacamole/payload/payload.img`
  (32 MiB, `payload_kernel_sha256=f9080dac...`) and
  `out/guacamole/boot/boot-32-r2.img` (38,748,160 bytes, sha256
  `391e199c...`, rebuilt FV `ddef072a...`). They are ready for a
  `fastboot boot` hardware test; no IPSW input is required.

## 2026-10-22: UniXNU menu had no XNU entry (payload volume missing)

- The rebuilt FV does contain `ShengBootMemoryDxe`, `UniXNU`, `UniXNUDxe`
  and `DarwinBoot` (FVMAIN GUIDs and `Guid.xref`). The menu that appeared was
  the application's built-in fallback (`Return to firmware`, `Restart`,
  `Power off`), not an Aloha BDS menu.
- Cause: `UniXNU` scans `SimpleFileSystem` volumes for
  `\EFI\UniXNU\unixnu.toml`. The payload FAT is the Android boot image
  ramdisk. The generated image had `ramdisk_addr = 0`; the stock Aloha image
  uses `0x1000000`. The OnePlus ABL does not add
  `/chosen/linux,initrd-start/-end` to this UEFI DTB (the Aloha DTB only has
  `bootargs`), so `ShengBootMemoryDxe` had no initrd to publish.
- Fix in `board.toml`: `ramdisk_offset = 0x1000000`. `scripts/build-bootimg.py`
  now also patches the first FDT of the multi-FDT table (preserving the
  appended tables) with `linux,initrd-start = 0x1000000` and
  `linux,initrd-end = 0x3000000` for the 32 MiB payload.
- Built and booted: `boot-32-r3.img` (ramdisk address only) and
  `boot-32-r4.img` (address + DTB properties), both with rebuilt FV
  `ddef072a...`. r4 header: ramdisk 0x1000000/0x2000000, payload bytes match,
  first FDT props verified. r4 was started with `fastboot boot`; visual menu
  confirmation is pending.

## 2026-10-22: r5 fixes the missing DTB pointer (Info Block clobber)

- r4 still showed `no boot entry found`. Root cause: `BootShim.S` saved the
  DTB pointer from x0 at `0x9FFFF000`, but that address is the firmware
  **Info Block** in the guacamole memory map
  (`PlatformMemoryMapLib.c`: `"Info Blk", 0x9FFFF000`). By the time
  `ShengBootMemoryDxe` ran, x0 was gone, so it never saw
  `/chosen/linux,initrd-start/-end` and never published the payload FAT.
  The DTB patch in r4 was irrelevant because the pointer itself was clobbered.
- r5: `BootShim.S` stores x0 at `0x9FF92000`, the memory map's reserved
  `"RAM Partition"`; `ShengBootMemoryDxe` reads that address and, before
  publishing, removes the initrd range from the GCD so the DXE allocator
  cannot overwrite the FAT.
- Local build fixes needed for the FV: `firmware.py` used `fields` before
  assignment; `board.toml` needs `SHARED_CRYPTO_PATH` pointing at
  `{edk2}/CryptoPkg/Binaries/edk2-basecrypto-driver-bin_extdep` and
  `FDT = "guacamole.dtb"`; the EDK2 `BinWrappers/PosixLike` tools in this
  tree drop `$@` when `Conf/BaseToolsCBinaries` exists, so the extdep
  binaries were copied into `MU_BASECORE/BaseTools/Source/C/bin`.
- r5: `out/guacamole/boot/boot-32-r5.img`, sha256
  `94f823b7...`, FV `79b9dd77...`, ramdisk 0x1000000/0x2000000, first-FDT
  initrd props present, payload bytes match. Booted with `fastboot boot`.
  The `045e:066b` UEFI USB gadget disappeared after the 3 s menu timeout and
  the phone did not return to fastboot, which is consistent with UniXNU
  finding the XNU entry and entering DarwinBoot/XNU (`sweetusb=0` disables
  kernel USB). Screen confirmation pending.
- r6 (after r5 still showed `no boot entry found`): `ShengBootMemoryDxe`
  now falls back to walking the UEFI memory map and looking for the payload
  FAT32 boot sector by its `GUACESP` label. If the ABL loaded the 32 MiB
  payload anywhere in RAM this publishes it without trusting the DTB or the
  header address. Image `boot-32-r6.img`, sha256 `8f66b31a...`, FV
  `40c4020b...`; booted with `fastboot boot`.
- r6 still showed `no boot entry found`, so the scan did not find the FAT.
  Root cause: the ABL adds its RAM base **0x80000000** to the boot image
  offsets. `ramdisk_offset=0x1000000` therefore loaded at
  `0x81000000..0x83000000`, but the reserved `"Kernel"` region is
  `0x80000000..0x82A00000`; the 32 MiB payload ran into the `"DBI Dump"`
  MMIO window at 0x82A00000, so the ABL did not load it (the stock image's
  6-byte ramdisk did fit).
- r7: `ramdisk_offset=0x800000` -> physical `0x80800000..0x82800000`,
  inside the Kernel region after the ~5 MiB kernel/DTB. `build-bootimg.py`
  now writes the physical addresses (`abl_base + base + offset`) into
  `/chosen`. Header ramdisk_addr 0x800000, first-FDT props
  0x80800000/0x82800000, payload bytes match. Image `boot-32-r7.img`,
  sha256 `04967862...`, FV `40c4020b...`; booted with `fastboot boot`.
- r9 status on screen: `d1 i1 s0 @836ff000`. The ABL patched the DTB
  `/chosen` and loaded the 32 MiB payload at physical **0x836ff000** (not the
  header offset/base); `ShengBootMemoryDxe` validated the `GUACESP` FAT boot
  sector and published the block device (`i1`). The scan did not run (`s0`).
- r10 volume diagnostic: `volumes 8`, `guac 0`; the app sees 8
  SimpleFileSystem volumes but none reports a `GUACESP` label. The payload
  block device exists, so the open question is whether FatDxe bound it (or
  only the label is missing).
- r11: `OpenPath` now strips leading backslashes before `Root->Open` (the
  config PCD is `\EFI\UniXNU\unixnu.toml`; some FAT/FV drivers reject an
  absolute-looking name on a volume root). Image `boot-32-r11.img`, sha256
  `1e6a086b...`, FV `b2e83b4b...`; booted with `fastboot boot`.
- r12: the payload block device was installed with
  `EFI_BLOCK_IO_MEDIA.LogicalPartition = FALSE` (whole disk), so the FV's
  `PartitionDxe` could bind it first and block `FatDxe`; the app saw only the
  FV/UFS SimpleFileSystem volumes (`guac 0`). The payload is a FAT volume
  image, so it is now marked `LogicalPartition = TRUE`; `PartitionDxe` skips
  it and `FatDxe` can bind directly. Image `boot-32-r12.img`, sha256
  `d72efed6...`, FV `867e1d9c...`; booted with `fastboot boot`.
- r13: actual reason the FAT volume never appeared (`guac 0` even with
  `i1 @836ff000`): the 32 MiB payload was FAT32 with only **64,496 clusters**,
  below the FAT32 minimum **65,525**. `fsck.vfat` warns and EDK2 `FatDxe`
  refuses to mount it; `ShengBootMemoryDxe` only checks the boot sector, so it
  still published the block device. `board.toml [payload] size_mib` is now
  **64**; the rebuilt payload has **129,022 clusters**, valid FAT32. Image
  `boot-32-r13.img`, sha256 `395b3345...`, 72,302,592 bytes; booted with
  `fastboot boot`.
- **r13 verified on hardware (2026-10-22):** the UniXNU menu now lists
  **"OnePlus 7 Pro - XNU"** and loads the config from the `GUACESP` payload
  FAT. The 32 MiB FAT32 was the last blocker; the earlier DTB pointer,
  ramdisk address, and FatDxe/PartitionDxe fixes were all required, but the
  invalid FAT32 cluster count was what kept the volume from mounting.

## 2026-10-25: iPadOS 17 bring-up from the XNU source kernel

Local Linux pipeline works: `scripts/linux/setup-toolchain.py` plus
`scripts/build-local-linux.sh` build the 4 KiB BCM2837 kernel (two XNU passes,
board archives, prelink, payload, boot image) in about 30 seconds per change.
Diagnostics that made the bring-up possible:

- `0904/0906/0907`: the panic saved state is drawn as large hex digits in the
  framebuffer (pc/lr/far/esr) through an `ml_io_map` window; the first fault of
  a boot wins, so nested panics do not overwrite it.
- `0914-0929`: a low-priority heartbeat thread redraws a counter and walks the
  blocked boot thread's kernel stack (frame pointers) into the framebuffer.
- `0941`: a wedged `vcputc_lock` is taken over instead of waited on, which
  restored the kernel console after the first kext starts.

Boot progression reached today (2026-10-25): XNU -> IOKit kexts -> MAC
policies (AppleImage4, AMFI, Sandbox, vnguard) -> `bsd_init` -> `dlil_init` ->
`setconf` -> the built-in SM8150 UFS driver -> HFS root mount -> first
`posix_spawn` of launchd (stalls with the iOS 16 userland from the r15 chain).

Findings and fixes:

- The "Unexpected fault in kernel static region" panic was our own diagnostic
  writing past the 2 MiB framebuffer V=P map; the marker/dump path now uses an
  `ml_io_map` window and a console-free strip.
- CoreTrust writes lazily initialized `__const` state during start; kext and
  kernel `__DATA_CONST` stay writable for the bring-up kernel (`0908`-`0910`).
- `MAC policy init failed: 1` was EPERM from `mac_policy_register` after
  `mac_late`: the `guac_skip_sec_ext` boot argument skipped the early security
  extension load, so AMFI/Image4 policies registered late. Removing it fixed
  the policy ordering.
- `kmem_alloc_contig` sleeps forever on this port (the kernel-managed range
  starts above 4 GiB and no contiguous run is available). The UFS DMA buffer
  now comes from a device-tree window (`ufs-dma`, PA 0x9e500000, 2 MiB),
  accessed byte-wise because the mapping is device memory (`0931`-`0936`).
- The SM8150 UFS driver reads the GPT, finds "userdata", and (with `0945`,
  `0946`) parses the SHNGROOT manifest written by
  `scripts/build-userdata-shngroot.py`: the OS window is exposed as
  `ufsroot0` with its exact byte length.
- iPadOS 17.7.11 userdata was rebuilt from the local IPSW with the APFS
  partition of each disk image as a window, and flashed with
  `fastboot flash userdata` (8.74 GiB).

Current blocker: APFS `open` of the root volume fails with ENOENT before any
block I/O. The container is exposed correctly (NXSB, nx_block_count matches the
window exactly, and the ADT root-matching UUID is present in the volume
superblock), so the failure is in APFS's root-vnode selection for the sealed
system volume, not in the block device. The r15 chain avoided this by mounting
an HFS+ root; a matching iPadOS 17 HFS+ root image (or the sealed-root snapshot
metadata from iBoot) is the next step.
