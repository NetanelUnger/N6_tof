"""Native proof for the existing manifest-only USB slot inspection path.

No hardware, signing key or firmware package is opened. Production updater,
XMODEM, Secure and FSBL code is executed with the existing test boundaries.
"""
from pathlib import Path
import sys
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
sys.path.insert(0,str(ROOT/'hil_tests'))
import test_xip_secure_update as secure
import test_firmware_update_drain as drain

SLOT_CASES=r'''
  /* Snapshot every modeled NOR byte, including both images and metadata. */
  static unsigned char no_write_snapshot[0x400000];
  for(unsigned active=0;active<2;active++) {
    fresh(&r);r.confirmed_slot=active;r.confirmed_version=51;
    manifest(&r.confirmed_manifest,active,51,active+1);save(&r,0);
    manifest(m,1-active,52,2-active);
    memcpy(no_write_snapshot,(void *)(uintptr_t)FW_FLASH_BASE_ADDRESS,sizeof no_write_snapshot);
    unsigned old_erases=erase_calls,old_writes=writes;
    m->flags=active+1;
    assert(SecureFirmwareUpdate_Begin(m,session)==SECURE_FW_UPDATE_ERROR_PARAMETER);
    m->flags=2-active;
    assert(SecureFirmwareUpdate_Begin(m,session)==0);
    assert(secure_update.active&&secure_update.target_slot==1-active);
    assert(!secure_update.bytes_erased&&!secure_update.bytes_written);
    assert(SecureFirmwareUpdate_Abort(*session+1)==SECURE_FW_UPDATE_ERROR_STATE);
    assert(secure_update.active);
    assert(SecureFirmwareUpdate_Abort(*session)==0&&!secure_update.active);
    assert(erase_calls==old_erases&&writes==old_writes);
    assert(!memcmp(no_write_snapshot,(void *)(uintptr_t)FW_FLASH_BASE_ADDRESS,sizeof no_write_snapshot));
    boot_metadata_load(&r,&bank);
    assert(r.state==FW_BOOT_STATE_CONFIRMED&&r.confirmed_slot==active&&r.confirmed_version==51);
    puts(active?"PASS B-confirmed: only A manifest accepted; abort preserves all NOR and confirmed51":
                "PASS A-confirmed: only B manifest accepted; abort preserves all NOR and confirmed51");
  }
'''

SHORT_BLOCK=r'''
static void short_block(uint8_t sequence,const uint8_t *data) {
  uint8_t packet[133]={1,0,0};packet[1]=sequence;packet[2]=255-sequence;
  memcpy(packet+3,data,128);uint16_t crc=0;
  for(unsigned i=0;i<128;i++) {crc^=(uint16_t)data[i]<<8;
    for(unsigned j=0;j<8;j++)crc=(crc&0x8000)?(uint16_t)((crc<<1)^0x1021):(uint16_t)(crc<<1);}
  packet[131]=(uint8_t)(crc>>8);packet[132]=(uint8_t)crc;
  Firmware_Update_Feed(packet,sizeof packet,tick);assert(last_control==6);
}
static void manifest_only(void) {
  tick=100;reset_count=writes=bytes_written=finalized=drained=0;
  FW_UpdateManifest_t manifest={0};manifest.image_size=1024;
  assert(sizeof manifest==256);
  assert(Firmware_Update_Start(output,&drained,"test",ready)==0);
  short_block(1,(const uint8_t *)&manifest);
  assert(!update_secure_session&&!writes&&!bytes_written&&!finalized&&!reset_count);
  short_block(2,(const uint8_t *)&manifest+128);
  assert(update_secure_session==1&&!writes&&!bytes_written&&!finalized&&!reset_count);
  assert(update_manifest_bytes==256&&update_image_bytes==0);
  uint8_t cancel[2]={0x18,0x18};Firmware_Update_Feed(cancel,2,tick);
  assert(!Firmware_Update_IsActive()&&!update_secure_session);
  Firmware_Update_Poll(tick+60000);
  assert(!writes&&!bytes_written&&!finalized&&!reset_count);
  puts("PASS exact two128-byte manifest packets plus CAN/CAN never call Write/Finalize/reset");
}
'''

def main():
    anchor='  assert(SecureFirmwareUpdate_Init()==0);'
    assert secure.EXTRA.count(anchor)==1
    secure.EXTRA=secure.EXTRA.replace(anchor,anchor+SLOT_CASES)
    secure.main()
    anchor='int main(void) {\n  transfer(100, ready);'
    assert drain.HARNESS.count(anchor)==1
    drain.HARNESS=drain.HARNESS.replace(anchor,SHORT_BLOCK+'\nint main(void) {\n  manifest_only();\n  transfer(100, ready);')
    drain.main()

if __name__=='__main__':main()
