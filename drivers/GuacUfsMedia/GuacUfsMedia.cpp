// SPDX-License-Identifier: BSD-2-Clause-Patent
// Guacamole: the UFS root window as an IOBlockStorageDevice. IOStorageFamily
// turns this into an IOMedia, which is what APFS's mount root requires.
// The IOBlockStorageDevice half is bound to the target kernelcache's own
// implementation (see scripts/data/native-ufs-original-bindings.S); reads are
// served by sweet_ufs's working UFS transport.
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/storage/IOBlockStorageDevice.h>
#include <kern/debug.h>
#include <kern/thread.h>

extern "C" void sweet_stage_field(uint64_t, uint64_t, uint64_t, uint64_t);

extern "C" int sweet_ufs_media_read(uint64_t off, void *dst, uint64_t len);
uint64_t guac_media_report[3] = {
	0xdead0000ULL, 0, 0
};
static char guac_media_bsdname[32];
static uint32_t guac_media_bdev;
volatile int guac_media_stage;


extern "C" const char *
guac_media_name(void)
{
	return guac_media_bsdname[0] ? guac_media_bsdname : nullptr;
}

extern "C" int
guac_media_rootdev(const char *name, uint32_t *dev)
{
	if (name == nullptr || dev == nullptr || guac_media_bdev == 0) {
		return -1;
	}
	if (strcmp(name, guac_media_bsdname) != 0) {
		return -1;
	}
	*dev = guac_media_bdev;
	return 0;
}
extern "C" uint64_t sweet_ufs_media_bytes(void);
extern "C" uint32_t sweet_ufs_media_block_size(void);

class GuacUfsMedia : public IOBlockStorageDevice {
	OSDeclareDefaultStructors(GuacUfsMedia)
public:
	bool start(IOService *provider) override;
	IOReturn doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block,
	    UInt64 count, IOStorageAttributes *attributes,
	    IOStorageCompletion *completion) override;
	IOReturn doEjectMedia() override;
	IOReturn doFormatMedia(UInt64 byteCapacity) override;
	UInt32 doGetFormatCapacities(UInt64 *capacities,
	    UInt32 capacitiesMaxCount) const override;
	char *getVendorString() override;
	char *getProductString() override;
	char *getRevisionString() override;
	char *getAdditionalDeviceInfoString() override;
	IOReturn reportBlockSize(UInt64 *blockSize) override;
	IOReturn reportEjectability(bool *isEjectable) override;
	IOReturn reportMaxValidBlock(UInt64 *maxBlock) override;
	IOReturn reportMediaState(bool *mediaPresent, bool *changedState) override;
	IOReturn reportRemovability(bool *isRemovable) override;
	IOReturn reportWriteProtection(bool *isWriteProtected) override;
};

OSDefineMetaClassAndStructors(GuacUfsMedia, IOBlockStorageDevice)

bool
GuacUfsMedia::start(IOService *provider)
{
	if (!IOBlockStorageDevice::start(provider)) {
		return false;
	}
	return true;
}

IOReturn
GuacUfsMedia::doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block,
    UInt64 count, IOStorageAttributes *, IOStorageCompletion *completion)
{
	uint64_t bytes = sweet_ufs_media_bytes();
	uint64_t bsize = sweet_ufs_media_block_size();
	uint64_t off = block * 512;
	uint64_t len = count * 512;
	IOReturn result = kIOReturnSuccess;

	if (buffer == nullptr || completion == nullptr || count == 0 ||
	    off > bytes || len > bytes - off) {
		return kIOReturnBadArgument;
	}
	if (buffer->getDirection() != kIODirectionIn) {
		return kIOReturnNotWritable;
	}
	if (buffer->getLength() < len) {
		return kIOReturnBadArgument;
	}
	/* UFS path I/O is 4 KiB aligned; copy through a per-call bounce. */
	uint64_t chunk = (uint64_t)bsize * 16;
	if (chunk == 0) {
		return kIOReturnNotReady;
	}
	void *bounce = IOMalloc((vm_size_t)(len < chunk ? len : chunk));
	if (bounce == nullptr) {
		return kIOReturnNoMemory;
	}
	uint64_t done = 0;
	while (done < len) {
		uint64_t want = (len - done) < chunk ? (len - done) : chunk;
		int error = sweet_ufs_media_read(off + done, bounce, want);
		if (error != 0) {
			result = kIOReturnIOError;
			break;
		}
		if (buffer->writeBytes(done, bounce, (vm_size_t)want) != want) {
			result = kIOReturnUnderrun;
			break;
		}
		done += want;
	}
	IOFree(bounce, (vm_size_t)(len < chunk ? len : chunk));
	if (completion->action != nullptr) {
		completion->action(completion->target, completion->parameter, result,
		    result == kIOReturnSuccess ? len : done);
	}
	return result;
}

IOReturn GuacUfsMedia::doEjectMedia(void) { return kIOReturnUnsupported; }
IOReturn GuacUfsMedia::doFormatMedia(UInt64) { return kIOReturnUnsupported; }
UInt32
GuacUfsMedia::doGetFormatCapacities(UInt64 *, UInt32) const
{
	return 0;
}
char *GuacUfsMedia::getVendorString(void) { return (char *)"UniXNU"; }
char *GuacUfsMedia::getProductString(void) { return (char *)"Guacamole UFS root"; }
char *GuacUfsMedia::getRevisionString(void) { return (char *)"1.0"; }
char *GuacUfsMedia::getAdditionalDeviceInfoString(void) { return (char *)""; }

IOReturn
GuacUfsMedia::reportBlockSize(UInt64 *blockSize)
{
	*blockSize = sweet_ufs_media_block_size();
	return kIOReturnSuccess;
}

IOReturn
GuacUfsMedia::reportEjectability(bool *isEjectable)
{
	*isEjectable = false;
	return kIOReturnSuccess;
}

IOReturn
GuacUfsMedia::reportMaxValidBlock(UInt64 *maxBlock)
{
	*maxBlock = sweet_ufs_media_bytes() / sweet_ufs_media_block_size() - 1;
	return kIOReturnSuccess;
}

IOReturn
GuacUfsMedia::reportMediaState(bool *mediaPresent, bool *changedState)
{
	*mediaPresent = true;
	if (changedState != nullptr) {
		*changedState = false;
	}
	return kIOReturnSuccess;
}

IOReturn
GuacUfsMedia::reportRemovability(bool *isRemovable)
{
	*isRemovable = false;
	return kIOReturnSuccess;
}

IOReturn
GuacUfsMedia::reportWriteProtection(bool *isWriteProtected)
{
	*isWriteProtected = true;
	return kIOReturnSuccess;
}

static void
guac_media_scan_thread(void *, wait_result_t)
{
	IOSleep(2000);
	OSDictionary *matching = IOService::serviceMatching("IOMedia");
	OSIterator *iterator = matching ? IOService::getMatchingServices(matching) : nullptr;
	uint64_t count = 0, name = 0, size = 0;
	while (iterator != nullptr && count < 8) {
		IOService *service = OSDynamicCast(IOService, iterator->getNextObject());
		if (service == nullptr) {
			break;
		}
		if (count == 0) {
			OSString *bsd = OSDynamicCast(OSString, service->getProperty("BSD Name"));
			OSNumber *bytes = OSDynamicCast(OSNumber, service->getProperty("Size"));
			if (bsd != nullptr) {
				const char *text = bsd->getCStringNoCopy();
				for (unsigned i = 0; i < 8 && text[i] != '\0'; i++) {
					name = (name << 8) | (unsigned char)text[i];
				}
			}
			if (bytes != nullptr) {
				size = bytes->unsigned64BitValue();
			}
		}
		count++;
	}
	if (iterator != nullptr) {
		iterator->release();
	}
	if (matching != nullptr) {
		matching->release();
	}
	sweet_stage_field(count, name, size, 0x5343414eULL);

	thread_terminate(current_thread());
}

extern "C" int
guac_ufs_media_publish(void)
{
	IOService *provider;
	GuacUfsMedia *media;
	OSDictionary *matching;
	guac_media_stage = 1;
	matching = IOService::serviceMatching("IOPlatformExpertDevice");
	if (matching == nullptr) {
		return -1;
	}
	guac_media_stage = 2;
	provider = IOService::waitForMatchingService(matching, 5000000000ULL);
	matching->release();
	if (provider == nullptr) {
		return -2;
	}
	guac_media_stage = 3;
	media = new GuacUfsMedia;
	if (media == nullptr) {
		return -3;
	}
	if (!media->init(nullptr)) {
		media->release();
		return -4;
	}
	guac_media_stage = 4;
	if (!media->attach(provider)) {
		media->release();
		return -5;
	}
	printf("GUACMEDIA: attach done, registering\n");
	guac_media_stage = 5;
	media->registerService(kIOServiceSynchronous);
	guac_media_stage = 6;
	printf("GUACMEDIA: registered\n");
	{
		/*
		 * The kernel console overwrites its last row, so park the answer in
		 * the fixed framebuffer fields instead: media count, first BSD name
		 * packed eight bytes per line, and its size.
		 */
			OSDictionary *matching = IOService::serviceMatching("IOMedia");
		OSIterator *iterator = matching ? IOService::getMatchingServices(matching) : nullptr;
		uint64_t count = 0, name = 0, size = 0;
		while (iterator != nullptr && count < 8) {
			IOService *service = OSDynamicCast(IOService, iterator->getNextObject());
			if (service == nullptr) {
				break;
			}
			if (count == 0) {
				OSString *bsd = OSDynamicCast(OSString, service->getProperty("BSD Name"));
				OSNumber *bytes = OSDynamicCast(OSNumber, service->getProperty("Size"));
				/* IOFindBSDRoot matches /chosen/root-matching by this UUID. */
				OSString *uuid = OSString::withCString("04769D26-2CA0-4825-B443-E2E5F88300F2");
				if (uuid != nullptr) {
					service->setProperty("UUID", uuid);
					uuid->release();
				}
				if (bsd != nullptr) {
					const char *text = bsd->getCStringNoCopy();
					for (unsigned i = 0; i < 8 && text[i] != '\0'; i++) {
						name = (name << 8) | (unsigned char)text[i];
					}
				}
				if (bytes != nullptr) {
					size = bytes->unsigned64BitValue();
				}
				OSNumber *maj = OSDynamicCast(OSNumber, service->getProperty("BSD Major"));
				OSNumber *min = OSDynamicCast(OSNumber, service->getProperty("BSD Minor"));
				if (bsd != nullptr) {
					strlcpy(guac_media_bsdname, bsd->getCStringNoCopy(), sizeof(guac_media_bsdname));
				}
				if (maj != nullptr && min != nullptr) {
					guac_media_bdev = (maj->unsigned32BitValue() << 24) |
					    (min->unsigned32BitValue() & 0xffffff);
				}
			}
			count++;
		}
		if (iterator != nullptr) {
			iterator->release();
		}
		if (matching != nullptr) {
			matching->release();
		}
		guac_media_report[0] = count;
		guac_media_report[1] = name;
		guac_media_report[2] = size;
	}
	{
		thread_t thread = nullptr;
		if (kernel_thread_start(guac_media_scan_thread, nullptr, &thread) == KERN_SUCCESS) {
			thread_deallocate(thread);
		}
	}
	return 0;
}
