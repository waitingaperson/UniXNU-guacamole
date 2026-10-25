# iPadOS 17.7.11 / XNU 10063 bring-up state (guacamole)

Last updated: 2026-10-25 (after the first live-fs root mount).

## What already works

1. UEFI/DarwinBoot hand-off, kernel entry, bsd_init, setconf.
2. `sweet_ufs` reads the SHNGROOT window correctly (host image and device
   bytes match; NXSB, checkpoint area and volume superblocks verified).
3. The root window is published as a real `IOMedia`:
   - `drivers/GuacUfsMedia/GuacUfsMedia.cpp` subclasses
     `IOBlockStorageDevice` using absolute bindings to the target
     kernelcache (`scripts/data/native-storage-bindings.S`).
   - The vtable was identified structurally (unique 176/176 kernel-export
     match). The metaclass, ctor, dtor and every used method are bound to
     their real entry points.
   - IOStorageFamily publishes `disk0` (whole, 0x16A400000 bytes, 4096).
4. `/chosen/root-matching` selects the APFS volume media (`disk1s1`,
   major 1 minor 2) exactly like the sheng reference.
5. APFS opens the volume, reads the container, and the **live root mounts**
   (`vfs_mountroot` returns 0). The post-mount `FSIOC_KERNEL_ROOTAUTH`
   ioctl returns EAUTH; `guac_skip_rootauth=1` lets boot continue.
6. Boot-stage markers reached so far: `set_rootvnode` (0x28), end of the
   auth block (0x29=41), devfs/siginit (0x49=73), end of bsd_init (0x2A=42).

## Where it stops

`bsd_utaskbootstrap()` -> `cloneproc()` -> `fork_create_child()`:
- Every step of `fork_create_child` completes (stage 0x61=97 is drawn).
- The final `thread_yield_internal(1)` never returns and the init thread
  never runs: `bsdinit_task` entry markers (slot 1: 43/44/45) are never
  drawn. `cpus=1` did not change this; replacing the yield with
  `IOSleep(100)` was the last experiment (result not yet observed).

Interpretation: the freshly cloned init thread is not scheduled (not on a
runqueue / never woken), so the cloning thread either blocks in the yield
or, with the yield removed, finishes bsd_init while process 1 never starts.

Open hypotheses:
- The cloned init thread is created waiting on `task_wait_to_return` and
  `task_clear_return_wait` does not make it runnable on this platform.
- Scheduler/timer/IPI support in the current 8796-era `ArmCpu`/timer
  patches is incomplete for the 10063 scheduler (the docs' platform page
  specifies the ArmCpu/ArmDTPlatform work: CPU registration, timer/GIC,
  secondary entry, IPI). This is the documented next porting step.

## Root authentication: what sheng does

Per <https://unixnu.com/zh/concepts/security>:
- UniXNU keeps Apple's security components and only provides the inputs
  they check (trust cache, chip seed, DT identity, PMGR, root policy).
- The root policy is the owner-signed VerifiedRoot package
  (`XNU_VERIFIED_ROOT_PROBE`, `XNU_OWNER_ROOT_AUDIT`,
  `XNU_OWNER_ROOT_TRUST`, `kits/VerifiedRoot`), plus
  `offline-owner-*` patches that publish `boot-manifest-hash`.
- Their own audits record that the unsealed restore OS root is refused by
  Apple's components and that they never booted iPadOS userspace from it.
  There is **no ADT switch** that disables APFS's root snapshot/auth check.

Our restore image (044-76040) is unsealed and has `num_snapshots = 0`, so
APFS's root-snapshot path cannot succeed. The only self-contained way to
the live fs is the kext patch in `scripts/patch-apfs-rootauth.py`:
- `root_hash_authentication_required` returns "not required"
  (`mov w20,#1` -> `#0`).
- `apfs_find_named_root_snapshot_xid` returns ENOENT instead of EAUTH when
  the forwarded payload is missing (`mov w19,#81` -> `#2`).
Both are applied to the prelinked kernel in `scripts/build-ipados.sh` and
are idempotent. This is a deliberate deviation from the official model.

## Build / patch pitfalls (important)

- The work tree is `out/guacamole/tree/.cache/xnu-work`, a clone of
  `refer/xnu` at `d8b8029` (xnu-10063.141.1).
- Patch order is **not** filename order: unixnu-named patches assume they
  are applied before the numeric `0xxx/09xx` patches. The tree's
  `.guacamole-applied` stamp now lists every patch that is already applied;
  do not delete it, or the loop re-applies in the wrong order and fails.
- Three superseded patches are intentionally absent: `0912-...kext-start`,
  `0913-...kext-init`, `native-dt-panic-region.patch`.
- The APFS kext bytes are patched after `emit_prelink.py`; if the target
  kernelcache changes, re-derive the vtable and the two code sites.
- Console does not scroll once the screen is full. Diagnostics must use the
  framebuffer fields:
  - `sweet_stage_slot(slot, value)` draws slot 0..3 at framebuffer rows
    1850/1950/2050/2150. Slot 0 = boot thread, slot 1 = `bsdinit_task`,
    slot 2 = exec.
  - `sweet_stage_field()` still draws the older four-line block (2400..).
  - The panic screen does not preserve those fields; do not rely on panic
    text after a full screen either.

## Stage map currently in the tree

| value | point |
|------:|-------|
| 10 | vfs_mountroot returned 0 |
| 20/30 | before/after IOSecureBSDRoot |
| 40 | set_rootvnode done |
| 41 | root-auth ioctl block done |
| 42 | end of bsd_init |
| 70..75 | imageboot/devfs/siginit/utaskbootstrap/pal_kernel_announce |
| 80..86 | bsd_utaskbootstrap: before cloneproc, after, proc_find, zalloc, signalend, ipc_task_enable, clear_return_wait |
| 90..97 | cloneproc: before forkproc, before/after fork_create_child, before pinsertchild, inside fork_create_child (task_create, proc_set_task, main_thread_create, final yield) |
| 43/44/45/46/47/50 (slot 1) | bsdinit_task: entry, current_proc, process_name, vm_init_before_launchd, bsd_do_post, before load_init_program |
| 60/61/80/90 (slot 2) | load_init_program loop and exec failure |

## Useful commands

```sh
./scripts/build-local-linux.sh                     # kernel + prelink + payload + image
fastboot boot out/guacamole/boot/boot-32-ipados-local.img
python3 scripts/patch-apfs-rootauth.py <prelinked.macho>   # idempotent
```

Boot args currently relevant: `root-live-fs=1`,
`allow-root-hash-mismatch=1`, `guac_skip_rootauth=1`, `cpus=1` (last test),
`rd=` absent (UUID root matching), `boot-uuid=04769D26-2CA0-4825-B443-E2E5F88300F2`.

## Next steps

1. Observe the `IOSleep(100)` experiment: does `bsdinit_task` (slot 1)
   start? If yes, the yield was the gate; keep a sleep or a proper wakeup.
2. If the init thread never runs, port the documented platform pieces
   (`ArmDTPlatform`, `ArmCpu` timer/GIC/IPI, SMMU) from the reference
   UniXNU-sheng sources instead of the older 8796-era patches, then retry
   the clone.
3. Only after process 1 runs: OS services (SystemOS/Data mounts) and the
   display path (`GopFramebuffer` + `NativeLegacyDisplay`, Aloha GOP) per
   <https://unixnu.com/zh/porting/display>.

## Restoring this exact source state

The cumulative diff of the working tree against `refer/xnu` commit
`d8b80295118ef25ac3a784134bcf95cd8e88109f` is stored as
`patches/xnu/zzz-current-state.patch` (~496 KiB). It applies to a clean
checkout in one step and contains every source change of this session,
including the direct edits that are not in the numbered patch files.

Restore procedure:

```sh
git -C out/guacamole/tree/refer/xnu worktree add ../../.cache/xnu-work2 d8b8029
git -C out/guacamole/tree/.cache/xnu-work2 apply <repo>/patches/xnu/zzz-current-state.patch
# then either point the build at xnu-work2, or move patches/xnu aside and
# let the build script skip the numbered series, or pre-populate
# .cache/xnu-work2/.guacamole-applied with every patch stamp.
```

The authoritative working tree is also committed in its own git repo
(`out/guacamole/tree/.cache/xnu-work`, commit `a540820`). Do not delete it
before the cumulative patch has been re-applied somewhere.

## Session log: last experiments

1. `cpus=1` + original `thread_yield_internal(1)`: boot thread stops at
   stage 0x61 (97), init thread never reaches 43 -> the yield waits for a
   thread that never becomes runnable.
2. `IOSleep(100)` instead of the yield: built and booted, but the result
   was not observed before shutdown. Next session should read the field
   rows (slot 1) from this image.
3. If slot 1 still shows nothing, port the platform pieces from the
   reference UniXNU-sheng sources (`ArmDTPlatform`, `ArmCpu` timer/GIC/IPI,
   SMMU) as the docs require, instead of extending the 8796-era patches.
