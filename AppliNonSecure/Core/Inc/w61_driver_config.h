#ifndef W61_DRIVER_CONFIG_H
#define W61_DRIVER_CONFIG_H

#include "config.h"

/* Explicit preparation/read-only validation images only. Normal builds retain
 * vendor configuration behavior. Never infer that same-value SET is read-only. */
#ifndef W61_CONFIG_PRESERVE
#define W61_CONFIG_PRESERVE       (0)
#endif

#define W61_WIFI_MAX_DETECTED_AP  (20U)
#define W61_NET_IPV6_ENABLE       (0)
#define W61_MAX_SPI_XFER          (1520U)

#include "logging.h"

#endif /* W61_DRIVER_CONFIG_H */
