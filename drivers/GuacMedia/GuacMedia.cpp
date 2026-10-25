// SPDX-License-Identifier: BSD-2-Clause-Patent
// Guacamole: a minimal IOKit node that advertises the UFS root window under the
// BSD device number sweet_ufs already publishes. APFS's root mount consults
// the IORegistry for the root media; this node gives it the BSD identity and
// the Apple_APFS content hint without pulling in IOStorageFamily classes
// (which live in the prelinked kexts and cannot be linked into the kernel).
#include <IOKit/IOService.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSBoolean.h>
#include <kern/debug.h>

class GuacMedia : public IOService {
	OSDeclareDefaultStructors(GuacMedia)
public:
	bool start(IOService *provider) override;
};

OSDefineMetaClassAndStructors(GuacMedia, IOService)

bool
GuacMedia::start(IOService *provider)
{
	if (!IOService::start(provider)) {
		return false;
	}
	return true;
}

static void
set_number(GuacMedia *media, const char *key, uint64_t value, unsigned bits)
{
	OSNumber *number = OSNumber::withNumber(value, bits);
	if (number) {
		media->setProperty(key, number);
		number->release();
	}
}

extern "C" int
guac_media_publish(uint32_t major, uint32_t minor, uint64_t size, uint32_t block_size)
{
	IOService *provider;
	GuacMedia *media;
	OSDictionary *matching;
	OSString *name;

	matching = IOService::serviceMatching("IOPlatformExpertDevice");
	if (matching == nullptr) {
		return -1;
	}
	provider = IOService::waitForMatchingService(matching, 5000000000ULL);
	matching->release();
	if (provider == nullptr) {
		return -2;
	}
	media = new GuacMedia;
	if (media == nullptr) {
		return -3;
	}
	if (!media->init(nullptr)) {
		media->release();
		return -4;
	}
	name = OSString::withCString("ufsroot0");
	if (name) {
		media->setProperty("BSD Name", name);
		name->release();
	}
	set_number(media, "BSD Major", major, 32);
	set_number(media, "BSD Minor", minor, 32);
	set_number(media, "Size", size, 64);
	set_number(media, "Block Size", block_size, 32);
	name = OSString::withCString("Apple_APFS");
	if (name) {
		media->setProperty("Content Hint", name);
		name->release();
	}
	/* APFS picks the root volume by matching this UUID. */
	name = OSString::withCString("04769D26-2CA0-4825-B443-E2E5F88300F2");
	if (name) {
		media->setProperty("UUID", name);
		name->release();
	}
	media->setProperty("Whole", kOSBooleanTrue);
	media->setProperty("Leaf", kOSBooleanTrue);
	media->setProperty("Writable", kOSBooleanTrue);
	media->setProperty("Removable", kOSBooleanFalse);
	media->setProperty("Ejectable", kOSBooleanFalse);
	if (!media->attach(provider)) {
		media->release();
		return -5;
	}
	media->registerService(kIOServiceSynchronous);
	return 0;
}
