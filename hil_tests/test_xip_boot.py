"""Native tests of the actual shared validator and FSBL state machine.

NOR and PKA are mocked; SHA256 and metadata CRC are actual firmware code.
This is host fault simulation, never evidence of physical power-cut safety.
"""
from pathlib import Path
import os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <assert.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "firmware_boot.c"
static unsigned erase_calls, writes, fail_write, reject_signature;
int EXTMEM_Read(unsigned memory,unsigned offset,unsigned char *out,unsigned length) {
  (void)memory; assert(offset+length<=0x400000); memcpy(out,(void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+offset),length);return 0;
}
int EXTMEM_Write(unsigned memory,unsigned offset,const unsigned char *in,unsigned length) {
  (void)memory; ++writes;
  if(fail_write) { memcpy((void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+offset),in,length/2);return -1; }
  memcpy((void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+offset),in,length);return 0;
}
int EXTMEM_EraseSector(unsigned memory,unsigned offset,unsigned length) {
  (void)memory; ++erase_calls;assert(offset==FW_METADATA_0_OFFSET||offset==FW_METADATA_1_OFFSET);
  memset((void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+offset),255,length);return 0;
}
int EXTMEM_MemoryMappedMode(unsigned a,unsigned b) {(void)a;(void)b;return 0;}
int32_t FW_Crypto_VerifyManifest(const FW_UpdateManifest_t *m) {
  return (FW_ManifestIsWellFormed(m)&&!reject_signature)?0:-1;
}
static void manifest(FW_UpdateManifest_t *m,unsigned slot,unsigned version,unsigned mode) {
  memset(m,0,sizeof *m); m->magic=FW_UPDATE_MANIFEST_MAGIC;m->format_version=1;m->header_size=sizeof *m;
  m->target_id=FW_UPDATE_TARGET_STM32N657;m->image_type=1;m->image_size=2048;m->firmware_version=version;m->flags=mode;
  unsigned char *p=(void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SlotOffset(slot));
  memset(p,0,2048);*(unsigned *)p=FW_STM32_IMAGE_MAGIC;*(unsigned *)(p+108)=2048-FW_STM32_IMAGE_PREFIX_SIZE;
  *(unsigned *)(p+0x400)=FW_NS_RAM_END;
  *(unsigned *)(p+0x404)=((mode==0)?FW_NS_RAM_START:FW_FLASH_BASE_ADDRESS+FW_SlotOffset(slot))+0x501;
  FW_SHA256(p,2048,m->image_sha256);
}
static void save(FW_BootRecord_t *r,unsigned bank) {
  FW_BootRecordSeal(r);memcpy((void *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+(bank?FW_METADATA_1_OFFSET:FW_METADATA_0_OFFSET)),r,sizeof *r);
}
static void fresh(FW_BootRecord_t *r) {
  memset((void *)(uintptr_t)FW_FLASH_BASE_ADDRESS,255,0x400000);FW_BootRecordMakeDefault(r);
  r->confirmed_version=11;manifest(&r->confirmed_manifest,0,11,0);save(r,0);writes=erase_calls=fail_write=reject_signature=0;
}
int main(void) {
  void *mapped=VirtualAlloc((void *)(uintptr_t)FW_FLASH_BASE_ADDRESS,0x400000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
  assert(mapped==(void *)(uintptr_t)FW_FLASH_BASE_ADDRESS);
  assert(FW_ImageVectorsAreValid(0,0,2048,1472,FW_NS_RAM_END,FW_NS_RAM_START+0x501));
  assert(FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_END,0x70180501));
  assert(FW_ImageVectorsAreValid(2,1,2048,1472,FW_NS_RAM_END,0x70280501));
  assert(!FW_ImageVectorsAreValid(1,1,2048,1472,FW_NS_RAM_END,0x70180501));
  assert(!FW_ImageVectorsAreValid(2,0,2048,1472,FW_NS_RAM_END,0x70280501));
  assert(!FW_ImageVectorsAreValid(3,0,2048,1472,FW_NS_RAM_END,0x70180501));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_START,0x70180501));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_END-1,0x70180501));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_END,0x70180500));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_END,0x701803ff));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1472,FW_NS_RAM_END,0x70180801));
  assert(!FW_ImageVectorsAreValid(1,0,2048,1471,FW_NS_RAM_END,0x70180501));
  assert(!FW_ImageVectorsAreValid(1,0,FW_SLOT_SIZE+1,0,FW_NS_RAM_END,0x70180501));
  puts("PASS 13 vector/slot/size/Thumb/stack contracts");
  FW_BootRecord_t r;unsigned bank;
  fresh(&r);assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  r.state=FW_BOOT_STATE_PENDING;r.pending_slot=1;r.pending_version=12;manifest(&r.pending_manifest,1,12,2);save(&r,0);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_B_OFFSET);
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_TRIAL&&r.confirmed_version==11);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  boot_metadata_load(&r,&bank);assert(r.state==FW_BOOT_STATE_CONFIRMED&&r.confirmed_version==11);
  puts("PASS actual FSBL RAM-to-XIP trial and unconfirmed-reset rollback");
  fresh(&r);r.state=FW_BOOT_STATE_PENDING;r.pending_slot=1;r.pending_version=12;manifest(&r.pending_manifest,1,12,2);save(&r,0);
  *(unsigned char *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_B_OFFSET+1200)^=1;
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  puts("PASS corrupted candidate cannot replace confirmed recovery");
  fresh(&r);r.state=FW_BOOT_STATE_PENDING;r.pending_slot=1;r.pending_version=12;manifest(&r.pending_manifest,1,12,1);save(&r,0);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  puts("PASS signed wrong-slot execution contract rejected by actual FSBL");
  fresh(&r);r.state=FW_BOOT_STATE_PENDING;r.pending_slot=1;r.pending_version=11;manifest(&r.pending_manifest,1,11,2);save(&r,0);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  puts("PASS non-increasing pending version rejected");
  fresh(&r);r.state=FW_BOOT_STATE_PENDING;r.pending_slot=1;r.pending_version=12;manifest(&r.pending_manifest,1,12,2);save(&r,0);
  fail_write=1;assert(Firmware_Boot_Prepare()!=0);fail_write=0;
  boot_metadata_load(&r,&bank);assert(bank==0&&r.state==FW_BOOT_STATE_PENDING&&r.confirmed_version==11);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_B_OFFSET);
  puts("PASS torn alternating-metadata write retains previous record and retries safely");
  fresh(&r);r.confirmed_slot=1;r.confirmed_version=12;manifest(&r.confirmed_manifest,1,12,2);
  r.pending_slot=0;r.pending_version=11;manifest(&r.pending_manifest,0,11,0);save(&r,0);
  *(unsigned char *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_B_OFFSET+1200)^=1;
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  puts("PASS corrupted confirmed XIP falls back to retained authenticated RAM image");
  fresh(&r);r.confirmed_slot=0;r.confirmed_version=13;manifest(&r.confirmed_manifest,0,13,1);
  r.pending_slot=1;r.pending_version=12;manifest(&r.pending_manifest,1,12,2);save(&r,0);
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_A_OFFSET);
  *(unsigned char *)(uintptr_t)(FW_FLASH_BASE_ADDRESS+FW_SLOT_A_OFFSET+1200)^=1;
  assert(Firmware_Boot_Prepare()==0&&Firmware_Boot_GetNonSecureSourceOffset()==FW_SLOT_B_OFFSET);
  puts("PASS XIP-A boot and XIP-B emergency fallback");
  VirtualFree(mapped,0,MEM_RELEASE);puts("PASS all 21 actual-C host cases (PKA/NOR mocked)");return 0;
}
'''
def run_native(harness=HARNESS, extra_stubs=None, extra_includes=(), retain_artifacts=False):
    if retain_artifacts:
        import contextlib
        retained=ROOT/'.local-dependencies/native-tests';retained.mkdir(parents=True,exist_ok=True)
        context=contextlib.nullcontext(tempfile.mkdtemp(prefix='resource-',dir=retained))
    else:
        context=tempfile.TemporaryDirectory(prefix='n6-xip-test-')
    with context as tmp:
        p=Path(tmp)
        (p/'test.c').write_text(harness)
        (p/'stm32_extmem.h').write_text('''#define EXTMEM_OK 0
#define EXTMEM_ENABLE 1
#define EXTMEM_DISABLE 0
int EXTMEM_Read(unsigned,unsigned,unsigned char *,unsigned);
int EXTMEM_Write(unsigned,unsigned,const unsigned char *,unsigned);
int EXTMEM_EraseSector(unsigned,unsigned,unsigned);
int EXTMEM_MemoryMappedMode(unsigned,unsigned);
''')
        (p/'stm32_extmem_conf.h').write_text('#define EXTMEMORY_1 0\n')
        for name,content in (extra_stubs or {}).items(): (p/name).write_text(content)
        # Reuse the unmodified production SHA functions; only hardware PKA is mocked.
        crypto=(ROOT/'Common/Update/firmware_crypto.c').read_text()
        constants=crypto[crypto.index('#define FW_ROTR32'):crypto.index('static const uint8_t fw_p256_prime')]
        functions=crypto[crypto.index('static uint32_t fw_load_be32'):crypto.index('int32_t FW_Crypto_Init')]
        (p/'sha.c').write_text('#include "firmware_crypto.h"\n#include <string.h>\n'+constants+functions)
        vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        vs=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
        includes=[p,ROOT/'Common/Update',ROOT/'FSBL/Core/Inc',ROOT/'FSBL/Core/Src',*extra_includes]
        flags=' '.join('/I"'+str(x)+'"' for x in includes)
        (p/'build.cmd').write_text('@echo off\ncall "'+str(Path(vs)/'VC/Auxiliary/Build/vcvars64.bat')+'" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W3 '+flags+' test.c sha.c "'+str(ROOT/'Common/Update/firmware_update_format.c')+'" /Fe:test.exe\n')
        subprocess.run(['cmd.exe','/d','/c',str(p/'build.cmd')],cwd=p,check=True)
        subprocess.run([str(p/'test.exe')],cwd=p,check=True)
if __name__=='__main__':run_native()
