// SPDX-License-Identifier: BSD-2-Clause-Patent
// Minimal sheng PMGR integration hook. The unixnu payload contract requires the
// kernel to define _sheng_pmgr_run before it will accept native-ufs-root=1; the
// guacamole UFS bring-up powers the controller itself, so this hook is a no-op.
const char sheng_pmgr_identity[] = "guac-sheng-pmgr";

void
sheng_pmgr_run(void)
{
}
