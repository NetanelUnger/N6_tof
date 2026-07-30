#ifndef W6X_CONFIG_H
#define W6X_CONFIG_H

/* Keep the NCP awake during first bring-up; BLE with the internal RC clock
 * also requires power save to be disabled. */
#define W6X_POWER_SAVE_AUTO             (0)
#define W6X_CLOCK_MODE                  (1U)
#define W6X_WIFI_AUTOCONNECT            (0)
#define W6X_WIFI_COUNTRY_CODE           "00"
#define W6X_WIFI_ADAPTIVE_COUNTRY_CODE  (0)
#define W6X_NET_DHCP                    (1U)
#define W6X_NET_HOSTNAME                "N6-ToF"
#define W6X_BLE_HOSTNAME                "N6-ToF-OTA"
#define W6X_NET_RECV_TIMEOUT            (10000U)
#define W6X_NET_SEND_TIMEOUT            (10000U)
#define W6X_NET_RECV_BUFFER_SIZE        (9216U)
#define W6X_HTTP_CLIENT_THREAD_STACK_SIZE (1536U)
#define W6X_HTTP_CLIENT_THREAD_PRIO     (30)
#define W6X_HTTP_CLIENT_TCP_SOCK_RECV_TIMEOUT (1000)
#define W6X_HTTP_CLIENT_TCP_SOCKET_SIZE (12288)
#define IPERF_ENABLE                    (0)
#define IPERF_V6                        (0)
#define MEM_PERF_ENABLE                 (0)
#define TASK_PERF_ENABLE                (0)

#endif /* W6X_CONFIG_H */
