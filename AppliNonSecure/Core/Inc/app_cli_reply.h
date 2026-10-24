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
  uint32_t active, generation, bytes, overflow, text_previous_cr;
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

/* Ordinary remote text: CR is a display line break; only the publisher may
 * append LF after the whole command. Preserve CRLF split across writes. */
static inline size_t AppCliReply_NormalizeText(uint8_t *target,
    const uint8_t *source, size_t length, uint32_t *previous_cr)
{
  size_t written = 0U;
  for (size_t i = 0U; i < length; ++i) {
    uint8_t byte = source[i];
    if (byte != '\n' || !*previous_cr) {
      if (target) target[written] = byte == '\n' ? '\r' : byte;
      ++written;
    }
    *previous_cr = byte == '\r';
  }
  return written;
}

static inline int AppCliReply_AppendText(AppCliReply_t *reply, uint8_t *first,
    size_t stride, size_t slot_size, size_t slot_count, const void *data,
    size_t length)
{
  if (!reply->active || (!data && length)) return -1;
  uint32_t previous_cr = reply->text_previous_cr;
  size_t amount = AppCliReply_NormalizeText(NULL, data, length, &previous_cr);
  size_t capacity = slot_size * slot_count;
  if (capacity < APP_CLI_REPLY_TRAILER_BYTES || reply->overflow ||
      reply->bytes > capacity - APP_CLI_REPLY_TRAILER_BYTES ||
      amount > capacity - APP_CLI_REPLY_TRAILER_BYTES - reply->bytes) {
    reply->overflow = 1U; return -1;
  }
  const uint8_t *source = data;
  for (size_t i = 0U; i < length; ++i) {
    uint8_t byte = source[i];
    if (byte != '\n' || !reply->text_previous_cr) {
      first[(reply->bytes / slot_size) * stride + reply->bytes % slot_size] =
          byte == '\n' ? '\r' : byte;
      ++reply->bytes;
    }
    reply->text_previous_cr = byte == '\r';
  }
  return 0;
}

static inline void AppCliReply_TrimLineBreak(AppCliReply_t *reply,
    const uint8_t *first, size_t stride, size_t slot_size)
{
  if (reply->bytes && first[((reply->bytes - 1U) / slot_size) * stride +
      (reply->bytes - 1U) % slot_size] == '\r') --reply->bytes;
}

#endif
