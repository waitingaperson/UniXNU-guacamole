// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
// Shared production window reader. Ops owns synchronization, block I/O,
// integrity verification and copying to the caller. No callback runs under
// this guard: the IOKit wrapper completes the request after this returns.
static bool ufsWindowGeometry (uint64_t absolute, uint64_t bytes)
{
  constexpr uint64_t limit = (uint64_t (UINT32_MAX) + 1) * 4096;
  return bytes && !(bytes & 511) && !(absolute & 4095) && absolute < limit && bytes <= limit - absolute;
}
struct UfsWindowResult { IOReturn status; uint64_t done; };
template <class Ops> struct UfsWindowGuard {
  Ops &ops;
  explicit UfsWindowGuard (Ops &value) : ops(value) { ops.lock (); }
  ~UfsWindowGuard () { ops.unlock (); }
  UfsWindowGuard (const UfsWindowGuard &) = delete;
  UfsWindowGuard &operator= (const UfsWindowGuard &) = delete;
};
template <class Ops>
static UfsWindowResult ufsReadWindow (Ops &ops, uint64_t absolute, uint64_t bytes,
                                     uint64_t block, uint64_t count, uint8_t *bounce)
{
  if (!bounce || !ufsWindowGeometry (absolute, bytes) || !count || block >= bytes / 512 || count > bytes / 512 - block)
    return { kIOReturnBadArgument, 0 };
  UfsWindowGuard<Ops> guard (ops);
  // start is an absolute LUN byte position; every integrity index below is
  // window-relative, so the two are kept explicitly apart.
  const uint64_t integrity = VR_BLOCK_BYTES;
  uint64_t start = absolute + block * 512, remaining = count * 512;
  UfsWindowResult result = { kIOReturnSuccess, 0 };
  while (remaining) {
    uint64_t position = start + result.done;
    uint64_t aligned = position - position % integrity;
    uint64_t skip = position - aligned;
    uint64_t needEnd = position + remaining;
    uint64_t blockEnd = needEnd + (integrity - needEnd % integrity) % integrity;
    if (blockEnd > absolute + bytes) blockEnd = absolute + bytes;
    uint64_t span = blockEnd - aligned;
    if (span > kDataMax) {
      span = kDataMax - kDataMax % integrity;
      if (span == 0) { result.status = kIOReturnBadArgument; break; }
    }
    uint64_t blocks = (span + 4095) / 4096;
    if (blocks > kDataMax / 4096) blocks = kDataMax / 4096;
    result.status = ops.read (aligned / 4096, static_cast<uint32_t> (blocks), bounce);
    if (result.status != kIOReturnSuccess) break;
    uint64_t verified = 0;
    while (verified < span) {
      uint64_t index = (aligned - absolute + verified) / integrity;
      uint64_t offset = index * integrity;
      if (offset >= bytes) { result.status = kIOReturnBadArgument; break; }
      uint64_t length = bytes - offset < integrity ? bytes - offset : integrity;
      if (verified + length > span) break;
      result.status = ops.verify (index, bounce + verified, static_cast<size_t> (length));
      if (result.status != kIOReturnSuccess) break;
      verified += length;
    }
    if (result.status != kIOReturnSuccess) break;
    if (verified <= skip) { result.status = kIOReturnBadArgument; break; }
    uint64_t usable = verified - skip;
    if (usable > remaining) usable = remaining;
    uint64_t copied = ops.copy (result.done, bounce + skip, usable);
    if (copied > usable) { result.status = kIOReturnIOError; break; }
    result.done += copied;
    if (copied != usable) { result.status = kIOReturnIOError; break; }
    remaining -= usable;
  }
  return result;
}
