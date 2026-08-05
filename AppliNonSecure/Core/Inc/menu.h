#ifndef MENU_H
#define MENU_H

/*
 * Small, allocation-free text command menu.
 *
 * A menu is a constant array of command-prefix/handler pairs.  Input may arrive
 * one byte at a time or in arbitrary chunks.  The module stores one command
 * line in a caller-owned buffer and invokes the matching handler only after a
 * carriage return or line feed has completed the command.
 *
 * Example:
 *
 *   static void device_turn_on(Menu_t *menu, const char *full_command);
 *   static void device_turn_off(Menu_t *menu, const char *full_command);
 *   static void tof_set_data(Menu_t *menu, const char *full_command);
 *
 *   static const Menu_Object_t main_menu_objects[] =
 *   {
 *     MENU_OBJECT("turn on", device_turn_on),
 *     MENU_OBJECT("turn off", device_turn_off),
 *     MENU_OBJECT("set tof", tof_set_data)
 *   };
 *
 * A line such as "set tof 123,123\r" calls tof_set_data() with the complete
 * string "set tof 123,123".  The handler can answer with Menu_Reply(), which
 * guarantees that the response ends in CRLF.
 */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Menu Menu_t;

typedef void (*Menu_CommandHandler_t)(Menu_t *menu,
                                      const char *full_command);

/*
 * The application-provided sender returns zero on success.  It must copy or
 * consume the text before returning; it must not retain the menu's reply
 * buffer pointer.
 */
typedef int32_t (*Menu_SendFunction_t)(const char *text, size_t length,
                                      void *context);

typedef struct
{
  const char *command;
  Menu_CommandHandler_t handler;
} Menu_Object_t;

typedef enum
{
  MENU_STATUS_OK = 0,
  MENU_STATUS_INVALID_ARGUMENT = -1,
  MENU_STATUS_INPUT_TOO_LONG = -2,
  MENU_STATUS_UNKNOWN_COMMAND = -3,
  MENU_STATUS_SEND_FAILED = -4,
  MENU_STATUS_REPLY_TOO_LONG = -5
} Menu_Status_t;

struct Menu
{
  const Menu_Object_t *objects;
  size_t object_count;
  Menu_CommandHandler_t unknown_handler;
  Menu_SendFunction_t send;
  void *send_context;
  char *input;
  size_t input_capacity;
  size_t input_length;
  char *reply;
  size_t reply_capacity;
  uint8_t discard_until_enter;
  uint8_t previous_was_cr;
};

#define MENU_OBJECT(command_text, command_handler) \
  { (command_text), (command_handler) }

#define MENU_OBJECT_COUNT(objects_array) \
  (sizeof(objects_array) / sizeof((objects_array)[0]))

/*
 * Initialize one menu instance.
 *
 * input_buffer and reply_buffer must be separate, non-overlapping arrays that
 * remain valid for the lifetime of the menu.  The reply buffer must be large
 * enough for the longest response plus CRLF.  No memory is allocated by this
 * module.  One task must own a Menu_t; the object is not internally locked.
 */
Menu_Status_t Menu_Init(Menu_t *menu,
                        const Menu_Object_t *objects,
                        size_t object_count,
                        char *input_buffer,
                        size_t input_capacity,
                        char *reply_buffer,
                        size_t reply_capacity,
                        Menu_SendFunction_t send,
                        void *send_context,
                        Menu_CommandHandler_t unknown_handler);

/*
 * Feed any number of newly received bytes to the menu.  A handler is called
 * synchronously when Enter ('\r', '\n', or "\r\n") completes a line.
 *
 * Backspace and Delete remove one pending byte.  If a command exceeds the
 * supplied buffer, the remainder of that line is discarded and
 * MENU_STATUS_INPUT_TOO_LONG is returned.
 */
Menu_Status_t Menu_Process(Menu_t *menu, const void *data, size_t length);

/* Forget the partially received command without changing the menu table. */
void Menu_Reset(Menu_t *menu);

/* Number of command bytes currently waiting for Enter. */
size_t Menu_GetPendingLength(const Menu_t *menu);

/* Read or replace the pending command line without dispatching it. */
const char *Menu_GetPendingInput(const Menu_t *menu);
Menu_Status_t Menu_SetPendingInput(Menu_t *menu, const char *text);

/*
 * Send one textual response through the callback supplied to Menu_Init().
 * Existing trailing CR/LF bytes are normalized and exactly one CRLF is added.
 */
Menu_Status_t Menu_Reply(Menu_t *menu, const char *text);

#ifdef __cplusplus
}
#endif

#endif /* MENU_H */
