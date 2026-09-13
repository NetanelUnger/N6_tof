#ifndef APP_FEATURES_H
#define APP_FEATURES_H

/*
 * Set this switch to 0 to remove the ST67W6X application thread at runtime.
 * The vendor driver remains part of the build, so re-enabling it is a
 * one-line change and does not require regenerating the CubeMX project.
 */
/* ST67W6X is not fitted on the current hardware setup.  Keep this at 0U so
 * neither its ThreadX application thread nor any W6X initialization runs. */
#define APP_ST67W6X_ENABLED  (0U)

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
