#include "menu.h"

#include <string.h>

static Menu_Status_t menu_dispatch(Menu_t *menu);
static const Menu_Object_t *menu_find_object(const Menu_t *menu,
                                             const char *command);
static uint32_t menu_is_delimiter(char value);

Menu_Status_t Menu_Init(Menu_t *menu,
                        const Menu_Object_t *objects,
                        size_t object_count,
                        char *input_buffer,
                        size_t input_capacity,
                        char *reply_buffer,
                        size_t reply_capacity,
                        Menu_SendFunction_t send,
                        void *send_context,
                        Menu_CommandHandler_t unknown_handler)
{
  size_t index;

  if ((menu == NULL) || (objects == NULL) || (object_count == 0U) ||
      (input_buffer == NULL) || (input_capacity < 2U) ||
      (reply_buffer == NULL) || (reply_capacity < 3U) || (send == NULL))
  {
    return MENU_STATUS_INVALID_ARGUMENT;
  }

  for (index = 0U; index < object_count; ++index)
  {
    if ((objects[index].command == NULL) ||
        (objects[index].command[0] == '\0') ||
        (objects[index].handler == NULL))
    {
      return MENU_STATUS_INVALID_ARGUMENT;
    }
  }

  menu->objects = objects;
  menu->object_count = object_count;
  menu->unknown_handler = unknown_handler;
  menu->send = send;
  menu->send_context = send_context;
  menu->input = input_buffer;
  menu->input_capacity = input_capacity;
  menu->input_length = 0U;
  menu->reply = reply_buffer;
  menu->reply_capacity = reply_capacity;
  menu->discard_until_enter = 0U;
  menu->previous_was_cr = 0U;
  menu->input[0] = '\0';
  menu->reply[0] = '\0';

  return MENU_STATUS_OK;
}

Menu_Status_t Menu_Process(Menu_t *menu, const void *data, size_t length)
{
  const uint8_t *bytes = (const uint8_t *)data;
  Menu_Status_t result = MENU_STATUS_OK;
  size_t index;

  if ((menu == NULL) || (menu->input == NULL) ||
      ((data == NULL) && (length != 0U)))
  {
    return MENU_STATUS_INVALID_ARGUMENT;
  }

  for (index = 0U; index < length; ++index)
  {
    uint8_t value = bytes[index];

    if ((value == (uint8_t)'\n') && (menu->previous_was_cr != 0U))
    {
      menu->previous_was_cr = 0U;
      continue;
    }
    menu->previous_was_cr = (value == (uint8_t)'\r') ? 1U : 0U;

    if ((value == (uint8_t)'\r') || (value == (uint8_t)'\n'))
    {
      if (menu->discard_until_enter != 0U)
      {
        menu->discard_until_enter = 0U;
        menu->input_length = 0U;
        menu->input[0] = '\0';
        continue;
      }

      if (menu->input_length != 0U)
      {
        Menu_Status_t dispatch_status = menu_dispatch(menu);
        if ((result == MENU_STATUS_OK) &&
            (dispatch_status != MENU_STATUS_OK))
        {
          result = dispatch_status;
        }
      }

      menu->input_length = 0U;
      menu->input[0] = '\0';
      continue;
    }

    if (menu->discard_until_enter != 0U)
    {
      continue;
    }

    if ((value == 0x08U) || (value == 0x7FU))
    {
      if (menu->input_length != 0U)
      {
        --menu->input_length;
        menu->input[menu->input_length] = '\0';
      }
      continue;
    }

    /*
     * Commands are text.  Accept printable ASCII, UTF-8 payload bytes, and
     * horizontal tab; ignore the other control characters.
     */
    if ((value < 0x20U) && (value != (uint8_t)'\t'))
    {
      continue;
    }

    if (menu->input_length >= (menu->input_capacity - 1U))
    {
      menu->discard_until_enter = 1U;
      menu->input_length = 0U;
      menu->input[0] = '\0';
      if (result == MENU_STATUS_OK)
      {
        result = MENU_STATUS_INPUT_TOO_LONG;
      }
      continue;
    }

    menu->input[menu->input_length++] = (char)value;
    menu->input[menu->input_length] = '\0';
  }

  return result;
}

void Menu_Reset(Menu_t *menu)
{
  if ((menu == NULL) || (menu->input == NULL))
  {
    return;
  }

  menu->input_length = 0U;
  menu->discard_until_enter = 0U;
  menu->previous_was_cr = 0U;
  menu->input[0] = '\0';
}

size_t Menu_GetPendingLength(const Menu_t *menu)
{
  if (menu == NULL)
  {
    return 0U;
  }

  return menu->input_length;
}

const char *Menu_GetPendingInput(const Menu_t *menu)
{
  if ((menu == NULL) || (menu->input == NULL))
  {
    return NULL;
  }
  return menu->input;
}

Menu_Status_t Menu_SetPendingInput(Menu_t *menu, const char *text)
{
  size_t length;

  if ((menu == NULL) || (menu->input == NULL) || (text == NULL))
  {
    return MENU_STATUS_INVALID_ARGUMENT;
  }

  length = strlen(text);
  if (length >= menu->input_capacity)
  {
    return MENU_STATUS_INPUT_TOO_LONG;
  }

  (void)memcpy(menu->input, text, length + 1U);
  menu->input_length = length;
  menu->discard_until_enter = 0U;
  menu->previous_was_cr = 0U;
  return MENU_STATUS_OK;
}

Menu_Status_t Menu_Reply(Menu_t *menu, const char *text)
{
  size_t length;

  if ((menu == NULL) || (menu->send == NULL) || (menu->reply == NULL) ||
      (text == NULL))
  {
    return MENU_STATUS_INVALID_ARGUMENT;
  }

  length = strlen(text);
  while ((length != 0U) &&
         ((text[length - 1U] == '\r') || (text[length - 1U] == '\n')))
  {
    --length;
  }

  if (length > (menu->reply_capacity - 3U))
  {
    return MENU_STATUS_REPLY_TOO_LONG;
  }

  if (length != 0U)
  {
    (void)memcpy(menu->reply, text, length);
  }
  menu->reply[length++] = '\r';
  menu->reply[length++] = '\n';
  menu->reply[length] = '\0';

  if (menu->send(menu->reply, length, menu->send_context) != 0)
  {
    return MENU_STATUS_SEND_FAILED;
  }

  return MENU_STATUS_OK;
}

static Menu_Status_t menu_dispatch(Menu_t *menu)
{
  const Menu_Object_t *object;
  char *command = menu->input;
  size_t length;

  while ((*command == ' ') || (*command == '\t'))
  {
    ++command;
  }

  length = strlen(command);
  while ((length != 0U) &&
         ((command[length - 1U] == ' ') || (command[length - 1U] == '\t')))
  {
    command[--length] = '\0';
  }

  if (length == 0U)
  {
    return MENU_STATUS_OK;
  }

  object = menu_find_object(menu, command);
  if (object != NULL)
  {
    object->handler(menu, command);
    return MENU_STATUS_OK;
  }

  if (menu->unknown_handler != NULL)
  {
    menu->unknown_handler(menu, command);
    return MENU_STATUS_OK;
  }

  return MENU_STATUS_UNKNOWN_COMMAND;
}

static const Menu_Object_t *menu_find_object(const Menu_t *menu,
                                             const char *command)
{
  const Menu_Object_t *best_match = NULL;
  size_t best_length = 0U;
  size_t index;

  for (index = 0U; index < menu->object_count; ++index)
  {
    const Menu_Object_t *candidate = &menu->objects[index];
    size_t candidate_length = strlen(candidate->command);

    if ((candidate_length > best_length) &&
        (strncmp(command, candidate->command, candidate_length) == 0) &&
        (menu_is_delimiter(command[candidate_length]) != 0U))
    {
      best_match = candidate;
      best_length = candidate_length;
    }
  }

  return best_match;
}

static uint32_t menu_is_delimiter(char value)
{
  return ((value == '\0') || (value == ' ') || (value == '\t')) ? 1U : 0U;
}
