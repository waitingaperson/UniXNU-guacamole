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

extern "C" int sweet_ufs_media_read(uint64_t off, void *dst, uint64_t len);
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

extern "C" int
guac_ufs_media_publish(void)
{
	IOService *provider;
	GuacUfsMedia *media;
	OSDictionary *matching;

	matching = IOService::serviceMatching("IOPlatformExpertDevice");
	if (matching == nullptr) {
		return -1;
	}
	provider = IOService::waitForMatchingService(matching, 5000000000ULL);
	matching->release();
	if (provider == nullptr) {
		return -2;
	}
	media = new GuacUfsMedia;
	if (media == nullptr) {
		return -3;
	}
	if (!media->init(nullptr)) {
		media->release();
		return -4;
	}
	if (!media->attach(provider)) {
		media->release();
		return -5;
	}
	printf("GUACMEDIA: attach done, registering\n");
	media->registerService(kIOServiceSynchronous);
	printf("GUACMEDIA: registered\n");
	{
		/* Report what IOStorageFamily has published so far. */
		OSDictionary *m;
		OSIterator *it;
		m = IOService::serviceMatching("IOMedia");
		it = m ? IOService::getMatchingServices(m) : nullptr;
		unsigned seen = 0;
		while (it != nullptr && seen < 8) {
			IOService *service = OSDynamicCast(IOService, it->getNextObject());
			OSString *bsd;
			OSNumber *size;
			if (service == nullptr) {
				break;
			}
			bsd = OSDynamicCast(OSString, service->getProperty("BSD Name"));
			size = OSDynamicCast(OSNumber, service->getProperty("Size"));
			printf("GUACMEDIA: media %s size=%llx\n",
			    bsd ? bsd->getCStringNoCopy() : "-",
			    size ? size->unsigned64BitValue() : 0ULL);
			seen++;
		}
		if (it != nullptr) {
			it->release();
		}
		if (m != nullptr) {
			m->release();
		}
		printf("GUACMEDIA: %u media service(s)\n", seen);
	}
	return 0;
}
