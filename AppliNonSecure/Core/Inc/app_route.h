#ifndef APP_ROUTE_H
#define APP_ROUTE_H

#include <stdint.h>

typedef enum
{
  APP_TRANSPORT_USB = 1,
  APP_TRANSPORT_BLE,
  APP_TRANSPORT_CLOUD,
  APP_TRANSPORT_SYSTEM
} AppTransport_t;

typedef struct
{
  AppTransport_t transport;
  uint32_t session_generation;
} AppRoute_t;

typedef uint32_t AppRequestId_t;

#endif /* APP_ROUTE_H */
