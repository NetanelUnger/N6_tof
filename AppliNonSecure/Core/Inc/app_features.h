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

/* The USB command console has its own small ThreadX thread as well. */
#define APP_USB_CLI_ENABLED  (1U)

#endif /* APP_FEATURES_H */
