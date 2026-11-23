/* The Cloud worker also owns the LAN listener and its single HTTP client.
 * LAN borrows the same command and image queues for an exclusive, volatile lease. */
#define LAN_LEASE_MS       (15000U)
#define LAN_COMMAND_MAX    (190U)
#define LAN_REQUEST_MS     (1200U)

UINT CloudRelay_RequestLan(const char *key)
{
  if (!cloud_initialized || !cloud_wifi_has_ip || cloud_recovery_pause ||
      strlen(key) != N6_LAN_KEY_LENGTH) return TX_NOT_AVAILABLE;
  for (size_t i = 0; i < N6_LAN_KEY_LENGTH; i++)
    if (!isxdigit((unsigned char)key[i])) return TX_NOT_AVAILABLE;

  if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return TX_NOT_AVAILABLE;
  UINT result = TX_NOT_AVAILABLE;
  if (lan.key[0] == '\0' && !cloud->active_command_id[0] &&
      !cloud->pair_pending && !training.active && !Firmware_Update_IsActive())
  {
    memcpy(lan.key, key, sizeof(lan.key));
    lan.deadline = HAL_GetTick() + LAN_LEASE_MS;
    result = TX_SUCCESS;
  }
  (void)tx_mutex_put(&cloud->gate);
  if (result == TX_SUCCESS) (void)tx_event_flags_set(&cloud_events, CLOUD_WAKE_FLAG, TX_OR);
  return result;
}

static int lan_reply(const char *status, const void *body, size_t size,
                     const void *payload, size_t payload_size)
{
  int length = snprintf(cloud->request, sizeof(cloud->request),
    "HTTP/1.1 %s\r\nConnection: close\r\nCache-Control: no-store\r\n"
    "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: POST, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type\r\nAccess-Control-Allow-Private-Network: true\r\n"
    "Content-Type: application/octet-stream\r\nContent-Length: %lu\r\n\r\n",
    status, (unsigned long)(size + payload_size));
  if (length <= 0 || (size_t)length >= sizeof(cloud->request)) return -1;
  return cloud_send_all(cloud->socket, cloud->request, (size_t)length) ||
         cloud_send_all(cloud->socket, body, size) ||
         cloud_send_all(cloud->socket, payload, payload_size);
}

static int lan_command(const uint8_t *line, size_t length)
{
  if (length > LAN_COMMAND_MAX) return -1;
  for (size_t i = 0; i < length; i++)
    if (line[i] < 32U || line[i] > 126U) return -1;

  /* The LAN endpoint carries text commands only. */
  while (length && *line == ' ') { line++; length--; }
  if (!length) return -1;
  if (strncasecmp((const char *)line, "update", 6U) == 0 ||
      strncasecmp((const char *)line, "Start UART Firmware Update", 26U) == 0)
    return -1;

  if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return 1;
  if (cloud->active_command_id[0] || Firmware_Update_IsActive())
  {
    (void)tx_mutex_put(&cloud->gate);
    return 1;
  }
  memset(&cloud->input, 0, sizeof(cloud->input));
  strcpy(cloud->input.command_id, "LAN");
  strcpy(cloud->active_command_id, "LAN");
  cloud->input.sequence = 1U;
  memcpy(cloud->input.data, line, length);
  cloud->input.data[length] = '\r';
  cloud->input.data[length + 1U] = '\n';
  cloud->input.length = (uint32_t)length + 2U;
  cloud->input_ready = 1U;
  (void)tx_mutex_put(&cloud->gate);
  return 0;
}

static void lan_poll(void)
{
  if (cloud->ack_pending) cloud->ack_pending = 0U;
  if (cloud->output_count)
  {
    CloudOutputSlot_t *slot = &cloud->output[cloud->output_head];
    uint8_t kind = slot->completed ? 2U : 1U;
    if (!lan_reply("200 OK", &kind, 1U, slot->data, slot->length))
    {
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      cloud->output_head = (cloud->output_head + 1U) % CLOUD_OUTPUT_SLOT_COUNT;
      cloud->output_count--;
      if (kind == 2U)
      {
        cloud->active_command_id[0] = '\0';
        cloud->hold_command = 0U;
      }
      (void)tx_interrupt_control(posture);
    }
    return;
  }
  if (cloud->tof_pending && TOF_App_GetStreamDestination() == TOF_STREAM_CLOUD)
  {
    uint8_t kind = 3U;
    if (!TofImage_Encode(cloud->tof_payload,
                        (size_t)cloud->tof_width * cloud->tof_height * sizeof(float),
                        &cloud->tof_info))
    {
      TofImage_Header(cloud->tof_header, &cloud->tof_info, 0U, 3U);
      /* Keep the encoded frame header contiguous with its record type. */
      uint8_t header[1U + TOF_IMAGE_HEADER_SIZE];
      header[0] = kind;
      memcpy(header + 1U, cloud->tof_header, TOF_IMAGE_HEADER_SIZE);
      (void)lan_reply("200 OK", header, sizeof(header), cloud->tof_payload,
                     cloud->tof_info.payload_length);
      cloud_release_tof();
      return;
    }
  }
  if (cloud->tof_pending) cloud_release_tof();
  (void)lan_reply("204 No Content", NULL, 0U, NULL, 0U);
}

static void lan_http(void)
{
  char *request = (char *)cloud->response;
  char *headers = strstr(request, "\r\n");
  char *body = strstr(request, "\r\n\r\n");
  if (!headers || !body) return;
  size_t header_length = (size_t)(body - request);
  body += 4;
  if (!strncmp(request, "OPTIONS /n6/lan HTTP/1.", sizeof("OPTIONS /n6/lan HTTP/1.") - 1U) ||
      !strncmp(request, "OPTIONS /n6/lan/close HTTP/1.", sizeof("OPTIONS /n6/lan/close HTTP/1.") - 1U))
  {
    (void)lan_reply("204 No Content", NULL, 0U, NULL, 0U);
    return;
  }
  int close = !strncmp(request, "POST /n6/lan/close HTTP/1.", sizeof("POST /n6/lan/close HTTP/1.") - 1U);
  if (!close && strncmp(request, "POST /n6/lan HTTP/1.", sizeof("POST /n6/lan HTTP/1.") - 1U))
  {
    (void)lan_reply("404 Not Found", NULL, 0U, NULL, 0U);
    return;
  }
  const char *field = (const char *)cloud_find_ci((const uint8_t *)headers,
                        header_length - (size_t)(headers - request) + 2U, "\r\nContent-Length:");
  size_t available = cloud->response_length - (size_t)(body - request);
  if (!field) return;
  const char *number = field + sizeof("\r\nContent-Length:") - 1U;
  while (*number == ' ' || *number == '\t') number++;
  char *end;
  unsigned long size = strtoul(number, &end, 10);
  if (!isdigit((unsigned char)*number) || memcmp(end, "\r\n", 2U) ||
      size != available || size < N6_LAN_KEY_LENGTH + 1U ||
      size > N6_LAN_KEY_LENGTH + 1U + LAN_COMMAND_MAX) return;

  unsigned int mismatch = (unsigned int)(body[N6_LAN_KEY_LENGTH] ^ '\n');
  for (size_t i = 0; i < N6_LAN_KEY_LENGTH; i++)
    mismatch |= (unsigned int)(body[i] ^ lan.key[i]);
  if (mismatch)
  {
    (void)lan_reply("403 Forbidden", NULL, 0U, NULL, 0U);
    return;
  }
  lan.deadline = HAL_GetTick() + LAN_LEASE_MS;
  if (close || size > N6_LAN_KEY_LENGTH + 1U)
  {
    if (close) lan.stop = 1U;
    int result = close ? 0 : lan_command((const uint8_t *)body + N6_LAN_KEY_LENGTH + 1U,
                                        size - N6_LAN_KEY_LENGTH - 1U);
    (void)lan_reply(result == 0 ? "204 No Content" : result > 0 ? "409 Conflict" :
                    "400 Bad Request", NULL, 0U, NULL, 0U);
    return;
  }
  lan_poll();
}

static int lan_request_ready(void)
{
  const char *request = (const char *)cloud->response;
  const char *end = strstr(request, "\r\n\r\n");
  if (!end) return 0;
  const uint8_t *field = cloud_find_ci(cloud->response, (size_t)(end - request) + 2U,
                                     "\r\nContent-Length:");
  if (!field) return 1;
  unsigned long size = strtoul((const char *)field + sizeof("\r\nContent-Length:") - 1U,
                              NULL, 10);
  return size > N6_LAN_KEY_LENGTH + 1U + LAN_COMMAND_MAX ||
         size <= cloud->response_length - (size_t)(end + 4 - request);
}

static void lan_step(void)
{
  uint32_t timeout = 30U;
  if (lan.listener < 0)
  {
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = PP_HTONS(N6_LAN_PORT);
    lan.listener = W6X_Net_Socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (lan.listener < 0) { lan.stop = 1U; return; }
    if (W6X_Net_Setsockopt(lan.listener, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        W6X_Net_Bind(lan.listener, (const struct sockaddr *)&address, sizeof(address)) ||
        W6X_Net_Listen(lan.listener, 1))
      lan.stop = 1U;
    return;
  }
  if (cloud->socket < 0)
  {
    struct sockaddr_in peer;
    cloud->socket = W6X_Net_TryAccept(lan.listener, (struct sockaddr *)&peer);
    if (cloud->socket < 0) return;
    cloud->response_length = 0U;
    cloud->http_deadline = HAL_GetTick() + LAN_REQUEST_MS;
  }
  if (!cloud->http_deadline) return;
  ssize_t count = W6X_Net_Recv(cloud->socket, cloud->response + cloud->response_length,
                              CLOUD_RESPONSE_SIZE - cloud->response_length, 0);
  if (count > 0) cloud->response_length += (uint32_t)count;
  cloud->response[cloud->response_length] = '\0';
  if (lan_request_ready())
  {
    lan_http();
    cloud->http_deadline = 0U;
  }
  else if (count == -1 || cloud->response_length == CLOUD_RESPONSE_SIZE ||
           (int32_t)(HAL_GetTick() - cloud->http_deadline) >= 0)
    cloud->http_deadline = 0U;
}

static int lan_process(uint32_t wifi_has_ip)
{
  if (!lan.key[0]) { lan.stop = 0U; return 0; }
  uint32_t epoch = cloud_network_epoch;
  if (!wifi_has_ip || (int32_t)(HAL_GetTick() - lan.deadline) >= 0 ||
      (cloud->status.lan_active && cloud->network_epoch != epoch))
    lan.stop = 1U;

  if (!cloud->status.lan_active)
  {
    if (cloud->active_command_id[0] || cloud->pair_pending || training.active)
      lan.stop = 1U;
    else
    {
      cloud_close_socket();
      if (cloud->socket >= 0) return 1;
      cloud_release_tof();
      TOF_App_ReleaseStream(TOF_STREAM_CLOUD);
      cloud->network_epoch = epoch;
      cloud->http_deadline = 0U;
      cloud->status.lan_active = 1U;
      cloud->status.generation++;
    }
  }
  if (lan.stop)
  {
    if (!cloud->status.lan_active)
    {
      if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return 1;
      memset(lan.key, 0, sizeof(lan.key));
      lan.stop = 0U;
      (void)tx_mutex_put(&cloud->gate);
      return 0;
    }
    cloud_close_socket();
    if (cloud->socket >= 0) return 1;
    if (lan.listener >= 0)
    {
      if ((int32_t)(HAL_GetTick() - lan.retry_tick) < 0) return 1;
      UINT posture = tx_interrupt_control(TX_INT_DISABLE);
      if (AppSettings_IsBusy()) { (void)tx_interrupt_control(posture); return 1; }
      W6X_Net_RequestScopeBegin(500U, NULL, 0U);
      (void)tx_interrupt_control(posture);
      /* Listening sockets must retire the server on the NCP. */
      int result = W6X_Net_Shutdown(lan.listener, 1);
      W6X_Net_RequestScopeEnd();
      if (result) { lan.retry_tick = HAL_GetTick() + 1000U; return 1; }
      lan.listener = -1;
    }
    if (tx_mutex_get(&cloud->gate, TX_NO_WAIT) != TX_SUCCESS) return 1;
    cloud_release_tof();
    TOF_App_ReleaseStream(TOF_STREAM_CLOUD);
    cloud->input_ready = cloud->input_delivered = cloud->ack_pending = 0U;
    cloud->output_head = cloud->output_tail = cloud->output_count = 0U;
    cloud->hold_command = cloud->output_sequence = 0U;
    cloud->active_command_id[0] = '\0';
    memset(lan.key, 0, sizeof(lan.key));
    lan.stop = 0U;
    cloud->status.lan_active = 0U;
    cloud->status.generation++;
    cloud->next_action_tick = HAL_GetTick();
    (void)tx_mutex_put(&cloud->gate);
    return 1;
  }
  if (cloud->socket >= 0 && !cloud->http_deadline)
  {
    cloud_close_socket();
    return 1;
  }
  UINT posture = tx_interrupt_control(TX_INT_DISABLE);
  if (AppSettings_IsBusy()) { (void)tx_interrupt_control(posture); return 1; }
  W6X_Net_RequestScopeBegin(CLOUD_HTTP_TIMEOUT_MS, &cloud_network_epoch, epoch);
  (void)tx_interrupt_control(posture);
  lan_step();
  W6X_Net_RequestScopeEnd();
  return 1;
}

