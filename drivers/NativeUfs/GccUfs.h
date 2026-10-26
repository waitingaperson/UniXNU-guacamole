// SPDX-License-Identifier: BSD-2-Clause-Patent
// GCC registers used by UFS. The SM8150 (guacamole) values are transcribed
// from the public Linux gcc-sm8150.c clock driver; the SM8550 values from
// gcc-sm8550.c are kept in the comments where they differ. No write is
// performed by NativeUfs: these are read for the bring-up inventory only.
#ifndef NATIVE_UFS_GCC_UFS_H
#define NATIVE_UFS_GCC_UFS_H

// Physical windows from the sheng board DT (clock-controller@100000, ufshc@1d84000).
#define GCC_BASE                      0x00100000ULL
#define UFS_HC_BASE                   0x01d84000ULL
#define UFS_HC_SIZE                   0x3000ULL

#define GCC_UFS_PHY_GDSCR             0x77004   /* SM8550; SM8150 gdsc block not in gcc-sm8150.c */
#define GCC_UFS_MEM_PHY_GDSCR         0x9e000

#define GCC_UFS_PHY_AXI_ENABLE        0x77010   /* SM8150 gcc_ufs_phy_axi_clk; SM8550 0x77018 */
#define GCC_UFS_PHY_AHB_ENABLE        0x77014   /* SM8150; SM8550 0x77024 */
#define GCC_UFS_PHY_TX_SYMBOL0_ENABLE 0x77028
#define GCC_UFS_PHY_RX_SYMBOL0_ENABLE 0x7702c
#define GCC_UFS_PHY_UNIPRO_CORE_ENABLE 0x77058  /* SM8150; SM8550 0x77068 */
#define GCC_UFS_PHY_ICE_CORE_ENABLE   0x7705c   /* SM8150; SM8550 0x77074 */
#define GCC_UFS_PHY_PHY_AUX_ENABLE    0x77090   /* SM8150; SM8550 0x770b0 */
#define GCC_UFS_PHY_RX_SYMBOL1_ENABLE 0x770cc
// bus_aggr_clk in the board DT: gcc_aggre_ufs_phy_axi_clk, halt/enable 0x770e4, HW clock gating bit1
#define GCC_AGGRE_UFS_PHY_AXI_ENABLE  0x770c0   /* SM8150; SM8550 0x770e4 */

#define GCC_UFS_BRANCH_ENABLE_BIT     0x1U

// gcc_ufs_phy_ahb_clk and gcc_aggre_ufs_phy_axi_clk set hwcg_bit=1 in
// gcc-sm8550.c (hwcg_bit=1 on SM8550; SM8150 branches use the same flag in
// gcc-sm8150.c), so CLK_OFF=1 on an idle branch is normal (hardware
// 2026-10-17, sheng, read ahb=80000003).
// The reset and RPMh/TCSR/QMP-PHY programming are not represented here: their
// semantics are not qualified and NativeUfs must not write them speculatively.
#endif
