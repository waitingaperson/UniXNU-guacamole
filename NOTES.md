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
- **Every CI build after the stage markers was only the bootstrap pass.**
  `0700-guacamole-skip-sctlr-check.patch` removes the block that follows the
  `MSR_SCTLR_EL1_X0`/`isb` pair, and `0800-guacamole-post-mmu-mark.patch`
  inserts the post-MMU marker at that same point. Once 0800 is applied, 0700
  is no longer reverse-applicable, so the driver's second invocation aborted
  at `git apply --reverse --check`; `|| true` in the workflow hid it. The
  uploaded r17-r34 kernels were bootstrap-pass links without the
  corecrypto/libpthread archives. `build-xnu-4k-baseline.sh` now stamps the
  sha256 of the patch series and rebuilds the worktree from a clean checkout
  only when the series changes, so the full pass is reached.
- **r35 is the first fully linked 4K kernel.** CI run `39783503700` completed
  the bootstrap pass, all five archives and the prelink step. Kernel
  `out/guacamole/kernel/kernel-8796-r35.macho`, 15,298,200 bytes, sha256
  `e9d2790f...`, no undefined symbols. Image
  `out/guacamole/boot/boot-32-r35.img`, 72,302,592 bytes, sha256
  `643c5cbb...`, payload `0a2e0d5b...`. It adds stage 21 after the TTBR1
  switch and stage 22 after the TTBR0/flush, to separate a bad `cpu_tte`
  from the low-VA marker path.
- **r36 adds a pre-switch page-table walk.** `guac_kva_exec_status()` walks
  `cpu_tte` for `arm_vm_init` and `sweet_stage_mark` and draws stage 24 (L1
  entry), 25 (L2 entry), 26 (L3 entry) or 27 (PXN) at x=1100 before the
  switch; no marker means the code that runs right after `msr TTBR1_EL1` is
  mapped executable. The same kernel also takes `guacboot1=1`, which keeps
  the bootstrap KVA root in TTBR1 as a control. CI run `39785844497`.
  - kernel `aebafc39...`, 15,298,200 bytes;
  - `boot-32-r36.img` sha256 `907f779a...`, payload `875214bc...`;
  - control `boot-32-r36b.img` sha256 `ebe9d9c8...`, payload `04cd73eb...`.
- **Static checks on the 4K tables do not reproduce a fault.** The built
  kernel's `sysreg_restore.tcr_el1` decodes to `TG0=4K`, `TG1=4K`,
  `T0SZ=T1SZ=26` (38-bit VA), IPS 40-bit, so the hardware root is L1 with
  the 8-bit index the code uses. A host model of `init_ptpages` plus
  `arm_vm_page_granular_*` over the real segment list maps `arm_vm_init`
  and `sweet_stage_mark` as valid executable 4K pages, and maps the boot
  stack (`__BOOTDATA`, `excepstack_top` at `0xfffffff007fb4000`) writable.
  The next discriminator is therefore the hardware marker, not more static
  analysis.

## 2026-10-22: 900E RAM reads locate the stop after arm_vm_init

- **The 900E Sahara memory-debug interface allows arbitrary physical reads.**
  `qdl ramdump` (linux-msm/qdl) collects the SBL crash dump; with a local
  patch (`QDL_MEM_READ=addr:len:path`) the same session reads any address.
  Reading `0x181004000` returns the kernel Mach-O header, so the crashed
  kernel's RAM is intact and inspectable without the panel.
- The dump itself is the SBL/AOP crash dump, not kernel RAM: `KMSG.txt` is
  empty, and the offered regions are OCIMEM/CODERAM/PIMEM/PMIC state. The
  useful read is the arbitrary one.
- **The 4K TTBR1 switch works.** In RAM: `kva_active = 1`,
  `cpu_ttep = 0x182381000`, `cpu_tte = 0xfffffff030781000`,
  `invalid_tte = 0xfffffff030780000`. Walking the live tables: L1[0xc0]
  points at `0x182382000`, L2[0x39] at `0x182387000`, and the PTE for
  `arm_vm_init` is `0x500001813eb683` (valid, AF, EL1-executable, correct
  PA). The boot stack pages are valid and writable. The r36 stage 25 was a
  false positive: the checker used `phystokv()` after `ptov_table` was
  filled, so it read the slid aperture instead of the bootstrap linear map.
- **The framebuffer in RAM shows the real markers.** Reading 2 MiB at
  `0x9c000000` and matching the stage colors shows 8, 1, 2, 5, 6, 7, 12,
  13, 14, 15, 16, 17, 18, 19, 20, 21, 22, plus the false 25. So
  `arm_vm_init` returns and `arm_init` reaches stage 16.
- **The kernel stops right after the serial boot-arg block.** The kernel log
  buffer (in `__DATA`, found at PA `0x181b05e0c`) ends at
  `[  250.679843]: Serial mode specified: 00000003`, and a boot with
  `serial=0` ends at the same line with `00000000`. `switch_to_serial_console`
  is therefore not the fault; the next calls are `PE_create_console()`
  (`check_for_panic_log` + `PE_initialize_console`) and `PE_init_printf`.
- r37 marks those calls: stage 28 after `PE_consistent_debug_inherit`, 29
  after `serial_init`, 30 after `kernel_startup_initialize_upto`, 31 after
  the serial block, 32 after `PE_create_console`, 33 after
  `PE_init_printf`. Stages 28-35 draw at y=220+((stage-28)&7)*20, x=300.

- **The stop is inside `PE_create_console()`.** r37's framebuffer (read from
  RAM) has stages 28, 29, 30 and 31 but not 32. At that point `kernel_map`
  is NULL, `startup_phase < KMEM`, `PE_putc` is NULL and `vinfo` is still
  zero, so the fault is in `check_for_panic_log()` or the early
  `initialize_screen()` mapping.
- **`check_for_panic_log()` touches a BCM2837 address that does not exist on
  SM8150.** `BCM2837.h` sets `PLATFORM_PANIC_LOG_PADDR = 0x3c0fc000`; the
  function maps it (`gPanicBase = 0xfffffff108e00000`, `gPanicSize =
  0x4000`) and then reads `eph_magic` and `bzero`s 16 KiB there. A 900E
  read of physical `0x3c0fc000` returns no data, so the kernel access is an
  external abort. The ADT has no `pram` node, so the DT path returns early.
- **The early `io_map()` also needs leaf tables that 4K never built.**
  `io_map()` before `STARTUP_SUB_KMEM` maps at `virtual_space_start` with
  `pmap_map_bd_with_options()`, which walks L1/L2/L3 and panics with "no
  PTE" when the leaf is missing; it does not allocate. `init_ptpages()`
  creates L1/L2 only. r38 pre-allocates 64 MiB of L3 tables at
  `dynamic_memory_begin` (`init_ptpages_leaf`) and sets
  `CONFIG_XNU_DT_PANIC_REGION=y` so the platform panic-log address is not
  used.

- **r38 gets through `PE_create_console()`.** With the DT panic-region path
  and the pre-allocated leaf tables, the panel shows stages 28, 29, 30, 31,
  32 and 33; `PE_init_printf` returns and `kprintf` now has a console.
  The kernel no longer resets: it **hangs after stage 33**, in the startup
  steps that follow (`cpu_machine_idle_init`, `PE_init_platform`,
  `ml_map_cpu_pio`, `cpu_timebase_init`, `PE_init_cpu`,
  `fiq_context_init`, the `dram-base`/`dram-size` lookups).
- r39 marks those calls as stages 34-40 (x=300 for 34/35, x=500 for 36-40,
  y=220+((stage-28)&7)*20). The 900E arbitrary read of physical
  `0x3c0fc000` returns no data, which confirms the BCM2837 panic-log address
  is not backed by memory on SM8150.
- **r39 reaches stage 40.** The panel shows 28-35 at x=300 and 36-40 at
  x=500: `cpu_machine_idle_init`, `PE_init_platform`, `ml_map_cpu_pio`,
  `cpu_timebase_init`, `PE_init_cpu`, `fiq_context_init` and the
  `dram-base`/`dram-size` lookups all return. The kernel still hangs, so the
  stop is after the dram lookups, in `gDramBase = *dram_base`,
  `early_random()`/`__stack_chk_guard`, `machine_conf()` or
  `kernel_bootstrap()`.
- r40 marks stage 41 after `gDramSize`, 42 after the stack guard, 43 at the
  top of `machine_startup` and 44 after `machine_conf()`.

- **r40 reaches stage 44.** The panel shows 28-35 at x=300, 36-43 at x=500
  and 44 at x=700. `gDramBase`/`gDramSize`, `early_random`, the stack guard
  and `machine_conf()` all complete. The hang is inside
  `kernel_bootstrap()` (or its first `printf`), which starts with
  `printf("%s\n", version)`; the panel shows no kernel text, so the console
  path is still suspect.
- r41 marks `kernel_bootstrap` as stages 45 (entry) through 55
  (`printf`, `scale_setup`, `vm_mem_bootstrap`,
  `kernel_startup_initialize_upto(OSLOG)`, `console_init`, `stackshot_init`,
  `sched_init`, `MACH_IPC`, `PMAP_ACTIVATE_KERNEL`, `mapping_free_prime`),
  using a saved boot_args pointer for the calls without an argument.

- **`serial=0` is what unlocks `kernel_bootstrap`.** With the r41 kernel and
  only `serial=0` changed, the panel shows stages 45-55: `printf(version)`,
  `scale_setup`, `vm_mem_bootstrap`, the OSLOG startup entries,
  `console_init`, `stackshot_init`, `sched_init`, MACH_IPC,
  `PMAP_ACTIVATE_KERNEL` and `mapping_free_prime` all return. The BCM2837
  serial console (`serial=3`) is the hang: the first `kprintf` writes to a
  UART that does not exist on SM8150. The default board args must drop
  `serial=3`.
- The hang is now after stage 55, in `machine_init`, `clock_init`,
  `code_signing_init`, `task_init`/`thread_init` or
  `kernel_thread_create`. r42 marks those as stages 56-63.

- **r42 reaches stage 63.** The x=900 column shows all eight bars
  (56-59 at y=300..360 and 60-63 overwriting 52-55 at y=220..280), so
  `machine_init`, `thread_machine_init_template`, `clock_init`,
  `thread_group_init`, `coalitions_init`, `code_signing_init`,
  `task_init` and `thread_init` all return. The hang is after
  `thread_init`, in `restartable_init`/`workq_init`/`turnstiles_init`/
  `exception_init`/`kernel_thread_create`.
- r43 marks those as stages 64-71 (x=1100, y=220..360).

- **r43 reaches stage 71.** The panel shows six columns: 28-35, 36-43,
  44-51, 52-59, 60-67 and 68-71 (x=300/500/700/900/1100/1300). So
  `restartable_init`, `workq_init`, `turnstiles_init`,
  `mach_init_activity_id`, `host_statistics_init`, `exception_init` and
  `kernel_thread_create` all return; the hang is after the context switch
  into `kernel_bootstrap_thread`, in `idle_thread_create`,
  `sched_startup`, `thread_daemon_init`, `thread_bind`, `mapping_adjust`,
  `clock_service_create` or `device_service_create`.
- r44 marks those as stages 72-79 (x=1300, y=220..360).

- **r44 reaches stage 75.** The x=1300 column shows the r43 colors for
  68-71 (cyan/magenta/gray/white) and the r44 colors for 72-75
  (black/orange/blue/green); 76-79 are absent. So
  `kernel_bootstrap_thread`, `idle_thread_create`, `sched_startup` and
  `thread_daemon_init` return; the hang is in
  `kernel_startup_initialize_upto(STARTUP_SUB_THREAD_CALL)` (the
  thread_call service), before `thread_bind`.
- r45 marks before/after that startup phase (80/81) and the following
  calls (82-86), with a new y=380 band for stages 80+.

- **The stage number is now drawn on the panel.** `sweet_stage.c` carries a
  5x7 digit font rendered at 10x in the top-left corner, refreshed on every
  `sweet_stage_mark`, so the last stage is read directly instead of
  decoding colors.
- **A marker above 2 MiB faults.** The bootstrap maps only the first 2 MiB
  of the framebuffer V=P; stage 80's y=380 block (2,188,800 bytes) was
  outside it, so the r46 boot died in the marker write and the number
  stayed at 75. All markers are now kept in the y=220..360 band
  (offset < 2 MiB); the real hang is still after stage 75, in the
  `STARTUP_SUB_THREAD_CALL` entries.
- r47 keeps the layout inside the window and adds per-entry markers
  87-94 in `thread_call_initialize`, `ipc_importance_thread_call_init`,
  `work_interval_subsystem_init` and `vm_analytics_init`.

- **r47 reaches stage 86.** The digit readout shows 86, so the
  THREAD_CALL phase, `thread_bind`, `mapping_adjust`,
  `clock_service_create`, `device_service_create` and
  `phys_carveout_init` all return. The hang is after
  `phys_carveout_init`, in the SYSCTL startup phase, the
  `vm_kernel_addrperm` random block, `PE_init_iokit`,
  `STARTUP_SUB_EARLY_BOOT`, `spllo()` or
  `initialize_screen(kPEAcquireScreen)`.
- r48 marks those as stages 95-102.

- **r48 reaches stage 96.** The digit shows 96, so the SYSCTL startup phase
  and the `vm_kernel_addrperm`/`early_random` block return; stage 97 (after
  `PE_init_iokit`) never appears. The hang is inside `PE_init_iokit()`:
  `PE_init_printf(TRUE)` (`vcattach`), `pe_prepare_images`,
  `InitIOKit(PE_state.deviceTreeHead)` or `ConfigureIOKit()`.
- r49 marks those internally as stages 104-109.

- **r49 reaches stage 108.** The digit shows 108, so `PE_init_iokit`'s
  `PE_init_printf(TRUE)`, `pe_prepare_images` and
  `InitIOKit(PE_state.deviceTreeHead)` all return; stage 109
  (`ConfigureIOKit`) never appears. `ConfigureIOKit` is
  `gRootNub->configureDefaults()`, i.e. `createNVRAM`,
  `serial-number` publishing or `generatePlatformUUID`.
- r50 marks `configureDefaults` (110-113) and `createNVRAM` (114-115).

- r50/r51 did not build: the first missed the `sweet_stage_mark` extern in
  `createNVRAM`, the second linked with C++ mangling because the extern was
  not `extern "C"`. r52 fixes both; it is the pending image for the next
  hardware test.

- r52 also failed (`extern "C"` is not allowed inside a function); r53 moves
  the declaration to file scope in `IOPlatformExpert.cpp` and builds
  cleanly. Image `out/guacamole/boot/boot-32-r53.img`, sha256
  `73f6f338...`, kernel `0b505b11...`, payload `1cf029c1...`. This is the
  next hardware test: the digit should show 111/112/113/114/115 and name
  the `configureDefaults` step.

- **r53 reaches stage 112.** The digit shows 112, so `createNVRAM` and the
  `serial-number` block return; stage 113 (after
  `generatePlatformUUID()`) never appears. The hang is inside
  `generatePlatformUUID`: `IORegistryEntry::fromPath("/chosen")`, the
  `unique-chip-id`/`chip-id` lookups, `SHA1Final`, `uuid_unparse` or
  `OSString::withCString`.
- r54 marks those as stages 116-122.

- **r54 stops at stage 119, inside SHA1.** The digit shows 119 (after the
  `chip-id` read, before `SHA1Final`). The kernel's SHA1 is
  `libkern/crypto/corecrypto_sha1.c`, which dereferences
  `g_crypto_funcs`; the source-corecrypto bootstrap registers that table
  from a `STARTUP(EARLY_BOOT)` entry, i.e. **after**
  `PE_init_iokit()`. `g_crypto_funcs` is still NULL there, so the SHA1
  call faults into a panic spin and the digit stays at 119.
- r55 moves `source_corecrypto14_bootstrap` to
  `STARTUP(SYSCTL, STARTUP_RANK_LAST)`: after the sysctl MIB init (so its
  `sysctl_register_oid` calls work) and before `PE_init_iokit` (so the
  platform UUID SHA1 has a registered crypto table).

- r55 moved that bootstrap to `STARTUP(SYSCTL, ...)` and regressed to
  stage 86: the corecrypto start itself does not complete at the SYSCTL
  phase (FIPS POST or the sysctl registration), and the boot never reaches
  the SYSCTL marker (95).
- r56 puts the crypto bootstrap back at `EARLY_BOOT` and skips the early
  `generatePlatformUUID()` on BCM2837 instead, so `PE_init_iokit` does not
  call into unregistered crypto. The UUID can be generated after
  `EARLY_BOOT` once the crypto start is understood.

- **r56 reaches stage 97.** The digit shows 97, so `PE_init_iokit` returns
  with the UUID skipped; stage 98 (`STARTUP_SUB_EARLY_BOOT`) never appears.
  The crypto bootstrap is the first EARLY_BOOT entry, so the remaining hang
  is most likely inside `corecrypto_kext_start` (FIPS POST or the sysctl
  registration).
- r57 marks around `corecrypto_kext_start` (123/124) and switches the UUID
  guard to `!APPLE_ARM64_ARCH_FAMILY`.

- **r57 stops at stage 123**, i.e. immediately before
  `corecrypto_kext_start`. The FIPS POST (`fipspost_post`) is the suspect:
  it returns immediately when the `fips_mode` DISABLE flag (0x4) is set.
  The bootstrap guard panics on any nonzero `fips_mode`, so r58 allows
  `fips_mode=4` and adds it to the board arguments; the POST is skipped and
  the KPI table is still registered.

- **r58 reaches stage 102.** `fips_mode=4` skips the FIPS POST,
  `corecrypto_kext_start` returns, EARLY_BOOT finishes, `spllo`,
  `initialize_screen(kPEAcquireScreen)`, the commpage and
  `mac_policy_initmach` all pass. The hang is after stage 102:
  `vnguard_policy_init`, the LOCKDOWN startup phase,
  `OSKextRemoveKextBootstrap`, `machine_lockdown`, `PE_lockdown_iokit`,
  `vm_set_restrictions` or `bsd_init`.
- r59 marks those as stages 125-131 (stages >= 128 reuse the x=300 column;
  the digit is authoritative).

- **r59 reaches stage 130.** `vnguard_policy_init`, the LOCKDOWN startup
  phase, `OSKextRemoveKextBootstrap`, `machine_lockdown`,
  `PE_lockdown_iokit` and `vm_set_restrictions` all return; stage 131
  (`bsd_init` returns) is never reached, so the hang is inside `bsd_init`.
  The prime suspect is the root mount: `sweet_ufs` must find `/sweet-ufs`
  and the `userdata` GPT partition, otherwise `vfs_mountroot` loops forever.
  The driver prints `SWEET UFS: ...` and bsd_init prints
  `cannot mount root, errno = ...`; the video console should show them.
- r60 marks `bsd_init` (132-140): kauth, MAC, bufferinit, IOKit time,
  vfsinit, sysctl_mib_init, bsd_autoconf, setconf and a successful
  vfs_mountroot.

- **r60 still shows 130, with no console text.** The `bsd_init` markers
  132-140 never appear, so the hang is before `kauth_init()`:
  `platform_stall_panic_or_spin`, `throttle_init()`, `printf(copyright)`
  or `dev_kmem_init()`. The video console is attached at stage 100 but
  draws nothing, so a console-path hang (the first `printf` after
  `initialize_screen(kPEAcquireScreen)`) is the leading suspect.
- r61 marks `bsd_init`'s entry, the stall call, `throttle_init`, the
  copyright `printf` and `dev_kmem_init` as stages 141-145.

- **r61 still shows 130.** Disassembly confirms the 141 marker is the first
  instruction sequence in `bsd_init`, so `bsd_init` is never entered. The
  only code between `vm_set_restrictions` (stage 130) and `bsd_init` is
  `kperf_init_early()`; that is the hang.
- r62 marks it (146/147) and skips `kperf_init_early()` on non-Apple builds
  (`APPLE_ARM64_ARCH_FAMILY`).

- **r62 reaches stage 136.** The kperf skip lets `bsd_init` run: 141-145
  and 132-136 (kauth, MAC, bufferinit, IOKit time, vfsinit) all draw. The
  hang is between `vfsinit()` and `sysctl_mib_init()` (stage 137):
  `proc_uuid_policy_init`, `mcache_init`/`mbinit`, `knote_init`,
  `eventhandler_init`, `aio_init`, `pthread_init`, `pshm/psem_cache_init`,
  `dlil_init`, `socketinit` or `domaininit`.
- r63 marks those as stages 148-157.

- **r63 reaches stage 156.** `proc_uuid_policy_init` returns; the hang is in
  `mcache_init()`, whose first line is `ml_wait_max_cpus()`. That sleeps
  until `max_cpus_initialized == MAX_CPUS_SET`, which only
  `ml_set_max_cpus()` sets; on Apple the platform expert calls it, and a
  native port has nobody to. `cpus=1` does not help because the wait is on
  the topology flag, not the boot argument.
- r64 calls `ml_set_max_cpus(topology_info.num_cpus)` at the end of
  `ml_parse_cpu_topology()` so the flag is published before `bsd_init`.

- r64 called `ml_set_max_cpus()` inside `ml_parse_cpu_topology()` and the
  phone reset to 900E early: the topology parse runs **before**
  `kernel_startup_bootstrap()` initializes the lock subsystem, so locking
  `max_cpus_lock` there faults. r65 moves the call to `machine_conf()`
  (after the locks are up and the topology is final).

- **r65 reaches stage 157.** `mcache_init()` now returns (`ml_wait_max_cpus`
  gets its flag from `machine_conf`); the hang is inside `mbinit()`
  (`bsd/kern/uipc_mbuf.c`). r66 adds stage markers 160-171 across `mbinit`.

- r66 failed to compile: the `sweet_stage_mark` prototype was spliced into
  `__private_extern__ void`, and two markers landed in `mbuf_mtypes_sync`.
  r67 fixes both and places markers 160-172 across `mbinit`.

- r67 still showed 157 because `sweet_stage_mark` returns early for
  `stage > 159` (the color table has 160 entries), so the `mbinit` markers
  never drew. r68 draws the number for stages past 159 and inserts markers
  173-177 at `mbinit` entry, after `microuptime` and after each
  `read_random`, which bisects the first lines of `mbinit`.

- **r68 reaches stage 166.** `mbinit` runs through the reads, `mbuf_table_init`,
  `slabstbl`, `mleak_activate`, `ml_wait_max_cpus` and the `mcl_paddr`
  allocation; the hang is `IOMapperIOVMAlloc()`: the platform expert
  registered a required system mapper, so `checkForSystemMapper()` sleeps in
  `waitForSystemMapper()` for an IOMMU that this port does not have. r69
  forces `IOMapper::setMapperRequired(false)` (`mcl_paddr_base` becomes 0,
  i.e. physical-address passthrough).

- r69 still stopped at 166: `IOMapper::gSystem` starts as `kUnknown` (1),
  which carries the wait mask, and `IOPlatformExpert::start` (the only
  `setMapperRequired` caller) runs after `mbinit`. r70 initializes `gSystem`
  to `kNoMapper` (0) so early clients take the physical passthrough path; a
  real `IOMapper::start()` still overwrites it.

- **r70 reaches stage 153.** `mbinit` and the following kqueue/event/aio/pthread/
  pshm/psem inits pass; the hang is between 153 and 154, i.e. `nwk_wq_init()`
  or `dlil_init()`. `dlil_init` creates its input/detacher threads and then
  `msleep`s until each has run once (`dlil_pending_thread_cnt`). r71 marks the
  dlil thread entry (178), the pending-count decrement (179) and the wait
  (180/181) to tell scheduler failure from a thread-side panic.

- r73 shows the framebuffer console: kprintf goes through `vcputc` once
  `PE_initialize_console(kPETextScreen)` asks for the text screen (the screen
  acquire otherwise runs in graphics mode and disables the text console).
  The visible panic is `Unable to find driver for this platform: "D22AP"` in
  `IOPanicPlatform::start` (`IOPlatformExpert.cpp:2341`): the kernel has no
  platform kext, so the catch-all personality matched. r74 makes the fallback
  subclass call `IOPlatformExpert::start` and log instead of panicking.

- **r74-r76 pass the platform match and the dlil wait.** The framebuffer text
  console works after `PE_initialize_console(kPETextScreen)`; the platform
  fallback (`IOPanicPlatform` -> generic `IOPlatformExpert`) lets IOKit
  continue. r76 reaches marker 187 (`ifnet_attach` returned) but the console
  text stops at `skip attaching fsw to lo0 using legacy TX model`; the next
  `printf` may be stuck in the console ring/flush path (single CPU, ticket
  locks, preemption on). r77 replaces the printf breadcrumbs with lock-free
  framebuffer markers 189-193 (`gif_init`, `pfloginit`, `ether_family_init`,
  `net_init_run`, `inittodr`); r78 adds 194 after `bpfattach`.
- `scripts/mkadt.py` has `compatible = sweet,display` commented out for now so
  AppleCLCD does not take over the display and hide the kernel console; GPU
  work is deferred. Restore it when the console is no longer needed.

- The console "freeze" at the fsw line is not a hang: `DEBUG_BSDINIT` is 0, so
  every `bsd_init_kprintf` is a no-op. r79 sets it to 1, printing each
  `bsd_init` step to the framebuffer console alongside the 189-194 markers.

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


## 2026-10-24: r15 chain re-verified, from-source status

- **The r15 chain boots to iOS again.** `boot-32-r15-retest.img` (ios-sweet
  `kernel.development.guacamole`, sha256 `f9080dac...`, with the generated
  guacamole ADT, the r15 kernel arguments and the NOSB firmware volume)
  reaches the iOS userland on hardware. This confirms the UEFI/DarwinBoot,
  the UFS root and HFS/AMFI on the phone are all intact.
- **The from-source 8796 kernel does not reach userspace yet.**
  - `mbinit`, dlil and `ifnet_attach` pass; `setconf` stops in the UFS DMA
    allocation (fixed by a `max_pnum < 4 GiB` early allocation in r90).
  - The prelink route is ruled out for this kernel: the ipados notes record
    `NativePrelink.plan` failing on `_vfs_getvfs_with_vfsops` and the missing
    `_kalloc_sparse_prelink_index_version` / `_native_prelink_security_init_version`
    exports ("Do not force the prelink"). Prelinking Apple kexts also pulls
    AMFI/AppleImage4 in, which panics on the absent mix-n-match policy.
  - The working ios-sweet kernel is monolithic (`SWEET HFS`, `SWEET AMFI`)
    and mounts the root as HFS on `/dev/ufsroot0`.
- Next for the from-source track: port the ios-sweet built-in patch set
  (0025 AMFI, 0026 HFS, 0015 trust cache, 0016 device-tree platform, 0029
  unsealed root, 0034 UFS DMA above 4 GiB, ...) into `patches/xnu` and add the
  `SWEET`/`ARM64_BOARD_CONFIG_SWEET` build defines.

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
