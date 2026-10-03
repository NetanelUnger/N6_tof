#ifndef APP_FEATURES_H
#define APP_FEATURES_H

/*
 * Set this switch to 0 to remove the ST67W6X application thread at runtime.
 * The vendor driver remains part of the build, so re-enabling it is a
 * one-line change and does not require regenerating the CubeMX project.
 */
/* The X-NUCLEO-67W61M1 is fitted and its SPI/AT identity path is validated.
 * Keep the Radio Manager enabled while BLE and Wi-Fi remain independently
 * staged below. */
#ifndef APP_ST67W6X_ENABLED
#define APP_ST67W6X_ENABLED          (1U)
#endif

/* Bring up the BLE maintenance GATT server independently from Wi-Fi.  The
 * current stage exposes the two logical UART services and advertises them;
 * application data routing is deliberately added in the following stage. */
#ifndef APP_ST67W6X_BLE_GATT_ENABLED
#define APP_ST67W6X_BLE_GATT_ENABLED  (1U)
#endif

/* Enable the module-resident Wi-Fi station and network services.  All W6X
 * control calls are serialized by the Radio Manager.  The development CLI
 * intentionally exposes the same Wi-Fi commands through USB, BLE and Cloud. */
#ifndef APP_ST67W6X_WIFI_SERVICES_ENABLED
#define APP_ST67W6X_WIFI_SERVICES_ENABLED (1U)
#endif

/* Outbound Cloud Relay CLI and independent ToF upload path. */
#ifndef APP_ST67W6X_CLOUD_RELAY_ENABLED
#define APP_ST67W6X_CLOUD_RELAY_ENABLED (1U)
#endif

/* INSECURE DEMO-ONLY transport. 0 sends pairing codes, bearer tokens, CLI
 * records and ToF frames in plaintext HTTP over TCP port 80. Keep this at 0
 * only on a trusted lab network; restore TLS before any customer/security
 * claim. This switch does not change the server's HTTPS configuration. */
#ifndef APP_ST67W6X_CLOUD_USE_TLS
#define APP_ST67W6X_CLOUD_USE_TLS (0U)
#endif

#if ((APP_ST67W6X_CLOUD_USE_TLS != 0U) && \
     (APP_ST67W6X_CLOUD_USE_TLS != 1U))
#error "APP_ST67W6X_CLOUD_USE_TLS must be 0 or 1"
#endif

/* If TLS is re-enabled, verify the server by default. Setting this to 0 is
 * an additional insecure diagnostic override, not an HTTP compatibility fix. */
#ifndef APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER
#define APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER (1U)
#endif

#if ((APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER != 0U) && \
     (APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER != 1U))
#error "APP_ST67W6X_CLOUD_TLS_VERIFY_SERVER must be 0 or 1"
#endif

#if (((APP_ST67W6X_BLE_GATT_ENABLED == 1U) || \
      (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U) || \
      (APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U)) && \
     (APP_ST67W6X_ENABLED != 1U))
#error "ST67 Wi-Fi/BLE services require APP_ST67W6X_ENABLED"
#endif

#if ((APP_ST67W6X_CLOUD_RELAY_ENABLED == 1U) && \
     (APP_ST67W6X_WIFI_SERVICES_ENABLED != 1U))
#error "Cloud Relay requires ST67 Wi-Fi services"
#endif

/* The round GC9A01 display uses its dedicated SPI4 bus and LCD control pins.
 * SPI5 remains reserved for the optional ST67W6X radio. */
#define APP_GC9A01_DISPLAY_ENABLED  (1U)

/* The USB command console has its own small ThreadX thread as well. */
#define APP_USB_CLI_ENABLED  (1U)

/* Stage 08 installs the STEdgeAI Neural-ART network and embeds its exact
 * weights in the signed Non-Secure image.  At runtime they are copied into
 * NPU SRAM6, so firmware A/B rollback also rolls back the matching model. */
#define APP_RPS_NPU_ENABLED  (1U)

#endif /* APP_FEATURES_H */
