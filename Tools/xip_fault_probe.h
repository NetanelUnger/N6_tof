#ifndef N6_XIP_FAULT_PROBE_H
#define N6_XIP_FAULT_PROBE_H
#include <stdint.h>
/* NS-only diagnostic hooks. No Secure API, peripheral write or timing policy. */
void XipProbe_Begin(uint32_t phase, uint32_t offset, uint32_t length);
void XipProbe_End(void);
void XipProbe_CaptureFault(uint32_t source,uint32_t prior_primask);
void XipProbe_ReportFault(void);
#endif
