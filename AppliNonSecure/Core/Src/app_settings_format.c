#include "app_settings.h"
#include <string.h>

/* Keep the bounded digit/CRC routines shared at -O3 instead of duplicating
 * constant-width specializations. No format, buffer, or deadline changes. */
#if defined(__GNUC__)
#define SETTINGS_NOINLINE __attribute__((noinline))
#else
#define SETTINGS_NOINLINE
#endif

void AppSettings_Scrub(void *data, size_t size)
{
  volatile uint8_t *p = (volatile uint8_t *)data;
  if (p != NULL) while (size-- != 0U) *p++ = 0U;
}

static SETTINGS_NOINLINE uint32_t settings_crc(const char *data, size_t size)
{
  uint32_t crc = UINT32_MAX;
  for (size_t i = 0U; i < size; ++i) {
    crc ^= (uint8_t)data[i];
    for (uint32_t bit = 0U; bit < 8U; ++bit)
      crc = (crc >> 1) ^ ((0U - (crc & 1U)) & 0xEDB88320U);
  }
  return ~crc;
}

static SETTINGS_NOINLINE void put_hex(char *out, uint32_t value, size_t digits)
{
  static const char hex[] = "0123456789ABCDEF";
  while (digits != 0U) { out[--digits] = hex[value & 15U]; value >>= 4; }
}

static SETTINGS_NOINLINE int get_hex(const char *in, size_t digits, uint32_t *value)
{
  uint32_t n = 0U;
  for (size_t i = 0U; i < digits; ++i) {
    uint32_t d = (uint8_t)in[i];
    if (d >= '0' && d <= '9') d -= '0';
    else if (d >= 'A' && d <= 'F') d = d - 'A' + 10U;
    else return 0;
    n = (n << 4) | d;
  }
  *value = n; return 1;
}

static int field_valid(const char *value, size_t capacity, uint16_t length)
{
  return length < capacity && value[length] == '\0' &&
         memchr(value, '\0', length) == NULL;
}

static int record_valid(const AppSettings_Record *r)
{
  if (r == NULL || r->version != APP_SETTINGS_VERSION || r->generation == 0U ||
      (r->flags & ~APP_SETTINGS_FLAGS_ALL) != 0U ||
      !field_valid(r->ssid, sizeof(r->ssid), r->ssid_length) ||
      !field_valid(r->password, sizeof(r->password), r->password_length) ||
      !field_valid(r->device_id, sizeof(r->device_id), r->device_length) ||
      !field_valid(r->workspace_id, sizeof(r->workspace_id), r->workspace_length) ||
      !field_valid(r->token, sizeof(r->token), r->token_length)) return 0;
  if ((r->flags & APP_SETTINGS_WIFI_PRESENT) == 0U) {
    if (r->ssid_length || r->password_length || (r->flags & APP_SETTINGS_WIFI_DESIRED)) return 0;
  } else if (!r->ssid_length) return 0; /* empty password is an open network */
  if ((r->flags & APP_SETTINGS_WIFI_REFERENCE) &&
      (!(r->flags & APP_SETTINGS_WIFI_PRESENT) || r->password_length)) return 0;
  if ((r->flags & APP_SETTINGS_CLOUD_PRESENT) == 0U) {
    if (r->device_length || r->workspace_length || r->token_length ||
        (r->flags & APP_SETTINGS_CLOUD_ENABLED)) return 0;
  } else if (!r->device_length || !r->workspace_length || !r->token_length) return 0;
  /* CWJAP currently quotes these fields without escaping. Reject bytes that
   * would escape that command, rather than changing authentication syntax. */
  const char *wifi[2]={r->ssid,r->password};
  const uint16_t wifi_sizes[2]={r->ssid_length,r->password_length};
  for(size_t i=0U;i<2U;++i) for(size_t j=0U;j<wifi_sizes[i];++j)
    if(wifi[i][j]=='\r' || wifi[i][j]=='\n' || wifi[i][j]=='"' || wifi[i][j]=='\\') return 0;
  const char *cloud_fields[3]={r->device_id,r->workspace_id,r->token};
  const uint16_t cloud_sizes[3]={r->device_length,r->workspace_length,r->token_length};
  for(size_t i=0U;i<3U;++i) for(size_t j=0U;j<cloud_sizes[i];++j)
    if((uint8_t)cloud_fields[i][j]<32U || (uint8_t)cloud_fields[i][j]==127U) return 0;
  return 1;
}

AppSettings_Result AppSettings_Encode(const AppSettings_Record *r,
    char *text, size_t capacity, size_t *length)
{
  const char *fields[5]; uint16_t sizes[5]; size_t size, at;
  if (length != NULL) *length = 0U;
  if (text == NULL || length == NULL || !record_valid(r)) return APP_SETTINGS_INVALID;
  fields[0]=r->ssid; fields[1]=r->password; fields[2]=r->device_id;
  fields[3]=r->workspace_id; fields[4]=r->token;
  sizes[0]=r->ssid_length; sizes[1]=r->password_length; sizes[2]=r->device_length;
  sizes[3]=r->workspace_length; sizes[4]=r->token_length;
  size = 67U; /* 28-byte header + five six-byte field envelopes + CRC8/! */
  for (size_t i=0U;i<5U;++i) size += 2U*sizes[i];
  if (size > APP_SETTINGS_TEXT_MAX || capacity < size) return APP_SETTINGS_INVALID;
  memcpy(text,"N6S1|",5U); put_hex(text+5U,r->generation,8U); text[13]='|';
  put_hex(text+14U,(uint32_t)size,4U); text[18]='|';
  put_hex(text+19U,r->flags,8U); text[27]='|'; at=28U;
  for (size_t i=0U;i<5U;++i) {
    put_hex(text+at,sizes[i],4U); at+=4U; text[at++]=':';
    for(size_t j=0U;j<sizes[i];++j){put_hex(text+at,(uint8_t)fields[i][j],2U);at+=2U;}
    text[at++]='|';
  }
  put_hex(text+at,settings_crc(text,at),8U); at+=8U; text[at++]='!';
  *length=at; return APP_SETTINGS_OK; /* no terminating NUL is written to FS */
}

AppSettings_Result AppSettings_Decode(const char *text, size_t length,
    AppSettings_Record *r)
{
  uint32_t total, flags, generation, crc, n, byte; size_t at=28U;
  char *fields[5]; uint16_t *sizes[5]; const size_t caps[5]={33U,64U,65U,65U,1025U};
  if (r == NULL) return APP_SETTINGS_INVALID;
  AppSettings_Scrub(r,sizeof(*r));
  if (text != NULL && length >= 67U && length <= APP_SETTINGS_TEXT_MAX &&
      !memcmp(text,"N6S",3U) && text[4]=='|' && text[3]!='1')
    return APP_SETTINGS_UNSUPPORTED; /* never replace a reserved future schema */
  if (text == NULL || length < 67U || length > APP_SETTINGS_TEXT_MAX ||
      memcmp(text,"N6S1|",5U) || text[13]!='|' || text[18]!='|' || text[27]!='|' ||
      text[length-1U]!='!' || !get_hex(text+5U,8U,&generation) ||
      !get_hex(text+14U,4U,&total) || total != length ||
      !get_hex(text+19U,8U,&flags) || !get_hex(text+length-9U,8U,&crc) ||
      settings_crc(text,length-9U)!=crc) return APP_SETTINGS_CORRUPT;
  if ((flags & ~APP_SETTINGS_FLAGS_ALL) != 0U) return APP_SETTINGS_UNSUPPORTED;
  fields[0]=r->ssid; fields[1]=r->password; fields[2]=r->device_id;
  fields[3]=r->workspace_id; fields[4]=r->token;
  sizes[0]=&r->ssid_length; sizes[1]=&r->password_length; sizes[2]=&r->device_length;
  sizes[3]=&r->workspace_length; sizes[4]=&r->token_length;
  r->version=APP_SETTINGS_VERSION; r->length=(uint16_t)length;
  r->generation=generation; r->flags=flags; r->crc32=crc;
  for(size_t i=0U;i<5U;++i) {
    if (at+6U>length-9U || !get_hex(text+at,4U,&n) || n>=caps[i] ||
        text[at+4U]!=':' || 2U*n>length-9U-at-6U) goto bad;
    at+=5U; *sizes[i]=(uint16_t)n;
    for(size_t j=0U;j<n;++j) {
      if(!get_hex(text+at,2U,&byte) || byte==0U) goto bad;
      fields[i][j]=(char)byte; at+=2U;
    }
    if(text[at++]!='|') goto bad;
  }
  if(at!=length-9U || !record_valid(r)) goto bad;
  return APP_SETTINGS_OK;
bad:
  AppSettings_Scrub(r,sizeof(*r)); return APP_SETTINGS_CORRUPT;
}
