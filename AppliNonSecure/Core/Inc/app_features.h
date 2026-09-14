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

/* Keep the module-resident Wi-Fi stack off until the TCP/UDP integration
 * stage.  BLE does not require W6X_WiFi_Init(). */
#ifndef APP_ST67W6X_WIFI_SERVICES_ENABLED
#define APP_ST67W6X_WIFI_SERVICES_ENABLED (0U)
#endif

#if (((APP_ST67W6X_BLE_GATT_ENABLED == 1U) || \
      (APP_ST67W6X_WIFI_SERVICES_ENABLED == 1U)) && \
     (APP_ST67W6X_ENABLED != 1U))
#error "ST67 Wi-Fi/BLE services require APP_ST67W6X_ENABLED"
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
