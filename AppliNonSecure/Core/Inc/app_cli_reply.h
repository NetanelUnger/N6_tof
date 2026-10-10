#ifndef APP_CLI_REPLY_H
#define APP_CLI_REPLY_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* Metadata only: response bytes live in the transport's existing TX slots.
 * A command owns those slots before execution. Keep room for an explicit
 * failure/completion record even if its handler emits excessive output. */
#define APP_CLI_REPLY_TRAILER_BYTES 128U
typedef struct {
  uint32_t active, generation, bytes, overflow;
} AppCliReply_t;

static inline int AppCliReply_Append(AppCliReply_t *reply, uint8_t *first,
                                     size_t stride, size_t slot_size,
                                     size_t slot_count, const void *data,
                                     size_t length, uint32_t trailer)
{
  const uint8_t *source = data;
  size_t capacity = slot_size * slot_count;
  if (capacity < APP_CLI_REPLY_TRAILER_BYTES) return -1;
  size_t limit = capacity - (trailer ? 0U : APP_CLI_REPLY_TRAILER_BYTES);
  if (!reply->active || (!data && length)) return -1;
  if ((!trailer && reply->overflow) || reply->bytes > limit || length > limit - reply->bytes) {
    reply->overflow = 1U;
    return -1; /* No partial append; earlier text stays owned. */
  }
  while (length) {
    size_t index = reply->bytes / slot_size;
    size_t offset = reply->bytes % slot_size;
    size_t amount = slot_size - offset;
    if (amount > length) amount = length;
    memcpy(first + index * stride + offset, source, amount);
    reply->bytes += (uint32_t)amount;
    source += amount;
    length -= amount;
  }
  return 0;
}

#endif
