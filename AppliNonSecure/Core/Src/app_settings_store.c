#include "app_settings_store.h"
#include <string.h>

#define SETTINGS_READ_CHUNK APP_SETTINGS_IO_CHUNK

static AppSettings_Result verify_slot(AppSettings_Store *s, const AppSettings_Io *io,
    unsigned slot, uint32_t expected_size)
{
  /* pending is retired after encode; reuse it for exact readback comparison.
   * Decode the fully verified encoded bytes only at the final commit point. */
  char *chunk=(char *)&s->pending; uint32_t size=0U;
  AppSettings_Result result=APP_SETTINGS_OK;
  if(io->size(io->context,slot,&size)) return APP_SETTINGS_IO;
  if(size!=expected_size) return APP_SETTINGS_CORRUPT;
  for(uint32_t offset=0U;offset<size;) {
    uint32_t count=size-offset; if(count>SETTINGS_READ_CHUNK) count=SETTINGS_READ_CHUNK;
    if(io->read(io->context,slot,offset,chunk,count)) { result=APP_SETTINGS_IO; break; }
    if(memcmp(chunk,s->text+offset,count)) { result=APP_SETTINGS_CORRUPT; break; }
    offset+=count;
  }
  AppSettings_Scrub(&s->pending,sizeof(s->pending)); return result;
}

static AppSettings_Result read_slot(AppSettings_Store *s, const AppSettings_Io *io, unsigned slot)
{
  uint32_t size=0U;
  if(io->size(io->context,slot,&size)) return APP_SETTINGS_IO;
  if(size<67U || size>APP_SETTINGS_TEXT_MAX) return APP_SETTINGS_CORRUPT;
  for(uint32_t offset=0U;offset<size;) {
    uint32_t count=size-offset; if(count>SETTINGS_READ_CHUNK) count=SETTINGS_READ_CHUNK;
    if(io->read(io->context,slot,offset,s->text+offset,count)) return APP_SETTINGS_IO;
    offset+=count;
  }
  return AppSettings_Decode(s->text,size,&s->pending);
}

AppSettings_Result AppSettings_StoreLoad(AppSettings_Store *s, const AppSettings_Io *io)
{
  uint32_t slots=0U,legacy=0U; AppSettings_Result r=APP_SETTINGS_ABSENT;
  if(!s->text) return APP_SETTINGS_INVALID;
  AppSettings_Scrub(&s->current,sizeof(s->current));
  s->active_slot=-1; s->loaded=0U;
  io->begin(io->context);
  if(io->inventory(io->context,&slots,&legacy) || (slots & ~3U)) { r=APP_SETTINGS_IO; goto done; }
  for(unsigned slot=0U;slot<2U;++slot) if(slots & (1U<<slot)) {
    AppSettings_Result got=read_slot(s,io,slot);
    if(got==APP_SETTINGS_IO) { r=got; goto done; } /* cannot choose newest without both views */
    if(got==APP_SETTINGS_UNSUPPORTED) { r=got; goto done; }
    if(got!=APP_SETTINGS_OK) { if(s->active_slot<0) r=APP_SETTINGS_CORRUPT; continue; }
    if(s->active_slot>=0) {
      uint32_t delta=s->pending.generation-s->current.generation;
      if(delta==0U) {
        if(memcmp(&s->pending,&s->current,sizeof(s->current))) { r=APP_SETTINGS_CORRUPT; goto done; }
        continue;
      }
      if(delta==0x80000000U) { r=APP_SETTINGS_CORRUPT; goto done; }
      if(delta>0x80000000U) continue;
    }
    s->current=s->pending; s->active_slot=(int)slot; r=APP_SETTINGS_OK;
  }
  if(s->active_slot<0 && slots==0U && legacy) r=APP_SETTINGS_LEGACY;
  if((r==APP_SETTINGS_OK || r==APP_SETTINGS_ABSENT) && io->confirm && io->confirm(io->context)) r=APP_SETTINGS_IO;
  if(r==APP_SETTINGS_OK || r==APP_SETTINGS_ABSENT) s->loaded=1U;
done:
  io->end(io->context);
  AppSettings_Scrub(&s->pending,sizeof(s->pending)); AppSettings_Scrub(s->text,APP_SETTINGS_TEXT_MAX);
  if(r!=APP_SETTINGS_OK) { AppSettings_Scrub(&s->current,sizeof(s->current)); s->active_slot=-1; }
  s->result=r; return r;
}

AppSettings_Result AppSettings_StoreCommit(AppSettings_Store *s, const AppSettings_Io *io,
    uint32_t writes_enabled)
{
  size_t length=0U; AppSettings_Result r; unsigned target;
  if(!s->text) return APP_SETTINGS_INVALID;
  if(!writes_enabled) { r=APP_SETTINGS_READ_ONLY; goto out; }
  if(!s->loaded) { r=s->result==APP_SETTINGS_OK ? APP_SETTINGS_IO : s->result; goto out; }
  s->pending.version=APP_SETTINGS_VERSION;
  s->pending.generation=s->current.generation+1U;
  if(!s->pending.generation) s->pending.generation=1U;
  r=AppSettings_Encode(&s->pending,s->text,APP_SETTINGS_TEXT_MAX,&length);
  if(r!=APP_SETTINGS_OK) goto out;
  target=s->active_slot==0 ? 1U : 0U;
  io->begin(io->context);
  /* An optional approved first-create check may reuse the text inventory union.
   * Re-encode after it retires, inside this same immutable operation budget. */
  if(io->admit) {
    if(io->admit(io->context)) r=APP_SETTINGS_IO;
    else r=AppSettings_Encode(&s->pending,s->text,APP_SETTINGS_TEXT_MAX,&length);
  }
  if(r!=APP_SETTINGS_OK) { /* admission failure issues no mutation */ }
  else if(io->replace(io->context,target,s->text,(uint32_t)length)) r=APP_SETTINGS_IO;
  else {
    r=verify_slot(s,io,target,(uint32_t)length);
    if(r==APP_SETTINGS_OK) r=AppSettings_Decode(s->text,length,&s->pending);
    if(r==APP_SETTINGS_OK && io->confirm && io->confirm(io->context)) r=APP_SETTINGS_IO;
    if(r==APP_SETTINGS_OK) { s->current=s->pending; s->active_slot=(int)target; s->result=r; }
  }
  io->end(io->context);
  /* A lost write/readback terminal leaves commit outcome unknown. Preserve
   * current RAM, but no next write until a complete explicit reload arbitrates. */
  if(r!=APP_SETTINGS_OK) { s->loaded=0U; s->result=r; }
out:
  AppSettings_Scrub(&s->pending,sizeof(s->pending)); AppSettings_Scrub(s->text,APP_SETTINGS_TEXT_MAX);
  return r;
}
