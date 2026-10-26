// SPDX-License-Identifier: BSD-2-Clause-Patent
//
// AMFI's ConfigurationSettings matches "ApplePMGRNub" from the IORegistry,
// safeMetaCasts the result against that class and then latches the AON
// security bit through the ApplePMGR readAon/writeAon helpers. Those helpers
// dispatch through the provider stored at nub+0x88 and return 0 when it is
// NULL (verified in the target kernelcache: ldr x0,[x0,#0x88]; cbz x0 ->
// mov w0,#0; ret), so publishing a real, provider-less ApplePMGRNub instance
// is enough: no PMGR register, clock or power state is touched. Called from
// bsd_init before the calendar init when XNU_SHENG_PMGR is set.
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <libkern/c++/OSMetaClass.h>
#include <libkern/c++/OSSymbol.h>
#include <pexpert/pexpert.h>

extern "C" volatile uint32_t guac_pmgr_stage = 0;

extern "C" void
sheng_pmgr_run(void)
{
	unsigned int mode = 1; // guac-pmgr-nub=0 disables the publication
	PE_parse_boot_argn("guac-pmgr-nub", &mode, sizeof(mode));
	if (mode == 0) {
		return;
	}
	guac_pmgr_stage = 1;

	const OSSymbol *name = OSSymbol::withCString("ApplePMGRNub");
	if (name == nullptr) {
		guac_pmgr_stage = 11;
		return;
	}
	guac_pmgr_stage = 2;
	OSObject *object = OSMetaClass::allocClassWithName(name);
	name->release();
	if (object == nullptr) {
		guac_pmgr_stage = 12;
		printf("GUACPMGR: ApplePMGRNub class is not available\n");
		return;
	}
	guac_pmgr_stage = 3;
	IOService *nub = OSDynamicCast(IOService, object);
	if (nub == nullptr || !nub->init()) {
		guac_pmgr_stage = 13;
		printf("GUACPMGR: ApplePMGRNub init failed\n");
		return;
	}
	guac_pmgr_stage = 4;
	OSDictionary *matching = IOService::serviceMatching("IOPlatformExpertDevice");
	if (matching == nullptr) {
		guac_pmgr_stage = 14;
		return;
	}
	IOService *provider = IOService::waitForMatchingService(matching, 5000000000ULL);
	if (provider == nullptr) {
		guac_pmgr_stage = 15;
		printf("GUACPMGR: no platform expert device\n");
		return;
	}
	guac_pmgr_stage = 5;
	if (!nub->attach(provider)) {
		guac_pmgr_stage = 16;
		printf("GUACPMGR: ApplePMGRNub attach failed\n");
		return;
	}
	guac_pmgr_stage = 6;
	nub->setName("guac-pmgr-nub");
	nub->registerService(kIOServiceSynchronous);
	guac_pmgr_stage = 7;
	printf("GUACPMGR: ApplePMGRNub published (provider-less)\n");
}
