/* SPDX-License-Identifier: MIT
 * SM8150 (guacamole): SDM8150 GCC + QSMMUv2 + DWC3 device mode. The Aloha UEFI
 * leaves USB powered and clocked in DEVICE role, so only the DWC3 takeover and
 * the CDC-ACM transport run here (inherited PHY/power).
 *
 * Sources: mainline gcc-sm8150.c (usb3_prim branch/GDSCR offsets), mainline
 * sm8250.dtsi (sibling USB3 IP: 0x0a600000/0xcd00, GIC 133). The SM8150 USB
 * app-SMMU stream id is not yet observed on hardware (0x0 = inherited
 * firmware/identity mapping, like the sm8250 DT); confirm from the live DT or
 * the Aloha UEFI state before trusting DMA isolation.
 */
#ifndef QUD_SM8150_H
#define QUD_SM8150_H
#define QUD_SOC_NAME "sm8150-inherited"
/* Development IDs inherited from m1n1, not a new product allocation. */
#define QUD_USB_VID 0x1209u
#define QUD_USB_PID 0x316du
#define QUD_USB_SERIAL "QcomXnuUsbDebug"
#define QUD_USB_PRODUCT "Qualcomm XNU Debug"
#define QUD_GCC_BASE 0x00100000ULL
#define QUD_GCC_BYTES 0x40000u
#define QUD_DWC3_BASE 0x0a600000ULL
#define QUD_DWC3_BYTES 0x100000u
#define QUD_SMMU_BASE 0x15000000ULL
#define QUD_SMMU_BYTES 0x100000ULL
#define QUD_STREAM_ID 0x0u
#define QUD_DMA_IOVA 0x90000000ULL
/* gcc_usb30_prim_master/sleep/mock_utmi + usb3_prim_phy_aux/com_aux. The last
 * two (0xf050/0xf054) come from the SM8150 clock driver and are unverified on
 * the UEFI hand-off; keep the firmware state (no cold init) as documented. */
#define QUD_GCC_CBCR_OFFSETS {0xf010u, 0xf014u, 0xf018u, 0xf050u, 0xf054u}
#define QUD_GCC_BCR_OFFSET 0xf000u
#define QUD_GCC_GDSCR_OFFSET 0xf004u
#define QUD_GCC_CFG_GDSCR_OFFSET 0xf008u
#define QUD_QSCRATCH_HS_PHY_CTRL_OFFSET 0xf8810u
#define QUD_QSCRATCH_VBUS_MASK ((1u << 20) | (1u << 28))
/* PSCI SYSTEM_RESET via SMC is not qualified on guacamole yet. */
#define QUD_PSCI_SMC_RESET 0
#endif
