# External tree patches

The build depends on two upstream checkouts that are not vendored here.

| Patch | Baseline | Applies in |
|---|---|---|
| `unixnu-guacamole.patch` | `UniXNU/UniXNU` `b6ae99c` | `unixnu/` |
| `darwinboot-guacamole.patch` | `UniXNU/DarwinBoot` `85332b3` | `unixnu/drivers/DarwinBoot/` |
| `aloha-guacamole.patch` | `Project-Aloha/mu_aloha_platforms` `0b798128` | `uefi/` |

## Apply

```sh
git -C unixnu apply ../patches/unixnu-guacamole.patch
git -C unixnu/drivers/DarwinBoot apply ../../../patches/darwinboot-guacamole.patch
git -C uefi apply ../patches/aloha-guacamole.patch
```

`aloha-guacamole.patch` adds the `ShengBootMemoryDxe` driver and the
guacamole boot-image resources, so it creates files; apply it to a clean
checkout.

## What each patch changes

`unixnu-guacamole.patch`

- `Config.c` / `Internal.h` / `UniXNULib.inf` / `Main.c`: always connect
  controllers for the application host, count `SimpleFileSystem` volumes,
  report whether the `GUACESP` label is present, and expose the shim status.
  These are the diagnostics that found the invalid FAT32 and the missing
  volume.
- `Volume.c`: open config files relative to the volume root (strip leading
  backslashes). Some FAT/FV drivers reject `\EFI\...` from `Root->Open`.
- `scripts/unixnu/bootimg.py`: accept the Aloha BootShim header, whose size
  field describes the FV rather than shim+FV.
- `scripts/unixnu/firmware.py`: build `defines` after `fields` exists, and
  substitute `{uefi}`, `{edk2}` and `{tree}` in define values.

`darwinboot-guacamole.patch`

- `DarwinBoot.c`: allocate the kernel window at a 32 MiB boundary plus
  `Kernel.Base & (32 MiB - 1)`. The guacamole XNU kernel uses 16 KiB pages,
  so `start.s` builds its bootstrap KVA mapping from 32 MiB L2 blocks. The
  upstream 2 MiB congruence maps the first fetch after `SCTLR_EL1.M` goes
  live 16 MiB away. 32 MiB is a multiple of the 2 MiB block used by 4 KiB
  kernels, so one rule covers both.

`aloha-guacamole.patch`

- `BootShim/BootShim.S`: alias `UEFI_BASE`/`UEFI_SIZE` to the driver's
  `FD_BASE`/`FD_SIZE`, and preserve the DTB pointer at `0x9FF92000` before
  firmware overwrites `0x9FFFF000`.
- `ShengBootMemoryDxe`: validate the DTB initrd as a `GUACESP` FAT32 volume,
  remove it from the GCD, publish it as a logical-partition block device,
  and fall back to scanning the UEFI memory map for the boot sector.
- Device DSC/FDF and `PlatformBuildNoSb.py`: add `ShengBootMemoryDxe`,
  `UniXNU`, `UniXNUDxe`, `DarwinBoot`, `FdtLib` and `UniXNULib` to the
  guacamole NOSB build.
- `Resources/`: guacamole boot-image configuration and `mkbootimg.py`.

## Kernel-8796 patch series

`patches/xnu/` is the device override for UniXNU's XNU module. It targets
`xnu-8796.141.3` and replaces UniXNU's iOS 17 patch set. The current 24
patches cover:

- the 4 KiB machine config, source corecrypto/pthread, ArmDTPlatform and
  ArmCpu base (`native-4k-*`, `source-*`, `non-apple-*`);
- 8796 build compatibility: `source-machine-layer`,
  `apple-only-cpu-tunables`, the non-Apple `kpc.c` stub, `CFLAGS_EXTRA`,
  clang `-MJ` compile records, and the new-clang/UIO backports;
- iOS 16 deployment and the libpthread 514 source builder in `scripts/`.

The series applies cleanly to a fresh `xnu-8796.141.3` worktree. The kernel
currently builds and seals; storage/display drivers and `[kernel.prelink]` are
the next porting stages.

## Refresh

After changing an external tree:

```sh
git -C unixnu diff -- . ':(exclude)drivers/DarwinBoot' > patches/unixnu-guacamole.patch
git -C unixnu/drivers/DarwinBoot diff > patches/darwinboot-guacamole.patch
git -C uefi add -N Platforms/AndromedaPkg/Driver/ShengBootMemoryDxe Resources
git -C uefi diff --binary -- . ':(exclude)MU_BASECORE' > patches/aloha-guacamole.patch
git -C uefi reset -- Platforms/AndromedaPkg/Driver/ShengBootMemoryDxe Resources
```
