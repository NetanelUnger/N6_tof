/* Included after cloud_relay.c's existing private types/prototypes.
 * One existing radio snapshot remains pinned until a matching durable ACK.
 * No credentials, new queues, payload buffers or persistent firmware writes. */
#if defined(__GNUC__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif
typedef struct {
  volatile uint32_t active, deadline, interval, next_sample;
  uint32_t next_poll, receiver_known, attempts, acknowledged, failures, goal;
  TOF_StreamDestination_t previous_route;
  char session[33];
} CloudTrainingContext_t;
static CloudTrainingContext_t training;

static int cloud_training_id(const char *value)
{
  uint32_t nonzero=0U;
  if (strlen(value)!=32U) return 0;
  for (uint32_t i=0;i<32U;i++) {
    if (!((value[i]>='0' && value[i]<='9') || (value[i]>='a' && value[i]<='f'))) return 0;
    nonzero|=(uint32_t)(value[i]!='0');
  }
  return nonzero!=0U;
}

static void cloud_training_stop(uint32_t failed)
{
  if (!training.active) return;
  training.active=0U;
  training.failures+=failed;
  if (cloud->http_kind==CLOUD_HTTP_TRAIN_FRAME) cloud_close_socket();
  if (cloud->tof_pending && cloud->tof_info.mode==TOF_IMAGE_TRAINING_N6DF) {
    ++training.failures; cloud_release_tof();
  }
  /* A newer USB/BLE owner must never be overwritten by capture cleanup. */
  if (TOF_App_GetRequestedStreamDestination()==TOF_STREAM_CLOUD && TOF_App_IsDatasetStreamEnabled()) {
    TOF_App_SetDatasetStreamDestination(0U,TOF_STREAM_CLOUD);
    TOF_App_RequestStream(training.previous_route);
  }
}

static void cloud_training_tick(void)
{
  if (training.active && ((int32_t)(HAL_GetTick()-training.deadline)>=0 ||
      TOF_App_GetRequestedStreamDestination()!=TOF_STREAM_CLOUD)) cloud_training_stop(0U);
}

uint32_t CloudRelay_IsTrainingFrameDue(void)
{
  return training.active && cloud_wifi_has_ip &&
      (int32_t)(HAL_GetTick()-training.deadline)<0 &&
      (int32_t)(HAL_GetTick()-training.next_sample)>=0;
}

void CloudRelay_GetTrainingStatus(CloudRelay_TrainingStatus_t *status)
{
  if (!status) return;
  UINT posture=tx_interrupt_control(TX_INT_DISABLE);
  memset(status,0,sizeof(*status));
  status->active=training.active;status->attempts=training.attempts;
  status->acknowledged=training.acknowledged;status->failures=training.failures;
  status->goal=training.goal;
  status->pending=(cloud && cloud->tof_pending && cloud->tof_info.mode==TOF_IMAGE_TRAINING_N6DF)?1U:0U;
  status->remaining_ms=training.active && (int32_t)(training.deadline-HAL_GetTick())>0 ? training.deadline-HAL_GetTick():0U;
  memcpy(status->session,training.session,sizeof(status->session));
  (void)tx_interrupt_control(posture);
}

static void cloud_training_control(int status,const uint8_t *body,size_t length)
{
  uint32_t now=HAL_GetTick();
  training.next_poll=now+1000U;
  if (status==204) { training.receiver_known=1U;cloud_training_stop(0U);return; }
  if (status!=200) {
    training.next_poll=now+60000U;
    if (status==404) training.receiver_known=0U;
    else {++training.failures;cloud_training_stop(0U);}
    return;
  }
  char session[33],boot[33],protocol[8];
  uint32_t remaining,rate,count,version;
  if (json_get_string(body,length,"sessionId",session,sizeof(session)) ||
      json_get_string(body,length,"bootId",boot,sizeof(boot)) ||
      json_get_string(body,length,"protocol",protocol,sizeof(protocol)) ||
      json_get_u32(body,length,"remainingMs",&remaining) ||
      json_get_u32(body,length,"remainingSamples",&count) ||
      json_get_u32(body,length,"rateHz",&rate) ||
      json_get_u32(body,length,"captureVersion",&version) ||
      !cloud_training_id(session) || !cloud_training_id(boot) || strcmp(protocol,"N6DF4") ||
      version!=1U || !remaining || remaining>600000U || !count || count>256U || rate<1U || rate>4U) {
    ++training.failures;cloud_training_stop(0U);return;
  }
  training.receiver_known=1U;
  if (training.active && strcmp(training.session,session)) cloud_training_stop(0U);
  if (!training.active) {
    TOF_StreamDestination_t destination=TOF_App_GetRequestedStreamDestination();
    if ((destination!=TOF_STREAM_NONE && destination!=TOF_STREAM_CLOUD) || TOF_App_IsDatasetStreamEnabled() || Firmware_Update_IsActive()) return;
    if (TOF_App_SetCaptureIdentity(boot)!=0) {++training.failures;return;}
    cloud_release_tof();
    UINT posture=tx_interrupt_control(TX_INT_DISABLE);
    training.previous_route=destination;
    memcpy(training.session,session,sizeof(training.session));
    training.attempts=training.acknowledged=training.failures=0U;
    training.goal=count;training.deadline=now+remaining;
    training.interval=1000U/rate;training.next_sample=now;
    training.active=1U;
    (void)tx_interrupt_control(posture);
    TOF_App_SetDatasetStreamDestination(1U,TOF_STREAM_CLOUD);
  } else {
    uint32_t candidate=now+remaining;
    if ((int32_t)(candidate-training.deadline)<0) training.deadline=candidate;
    training.goal=training.acknowledged+count;
  }
}

static void cloud_training_ack(int status,const uint8_t *body,size_t length)
{
  uint32_t stored=0U,frame=0U,timestamp=0U,crc=0U;
  char boot[33],actual_boot[33];
  TOF_App_GetCaptureIdentity(actual_boot);
  if (status==200 && !json_get_bool(body,length,"stored",&stored) && stored &&
      !json_get_u32(body,length,"frameId",&frame) && frame==cloud->tof_frame_id &&
      !json_get_u32(body,length,"timestampMs",&timestamp) && timestamp==cloud->tof_info.timestamp_ms &&
      !json_get_u32(body,length,"wireCrc32",&crc) && crc==cloud->tof_info.payload_crc32 &&
      !json_get_string(body,length,"bootId",boot,sizeof(boot)) && !strcmp(boot,actual_boot)) {
    ++training.acknowledged;cloud_release_tof();
    if (training.acknowledged>=training.goal) cloud_training_stop(0U);
  } else if (status==400 || status==401 || status==403 || status==409 || status==422) {
    cloud_training_stop(1U);
  } else {
    /* Unknown/lost reply retains the identical record for an idempotent retry.
     * Existing bounded network backoff and request budgets remain unchanged. */
    ++training.failures;cloud_backoff();
  }
}

static int cloud_training_next(void)
{
  char boot[33],path[128];uint32_t now=HAL_GetTick();
  if (training.active && cloud->tof_pending && cloud->tof_info.mode==TOF_IMAGE_TRAINING_N6DF) {
    TOF_App_GetCaptureIdentity(boot);
    (void)snprintf(path,sizeof(path),"/api/device/training/%s/%s/frames",training.session,boot);
    ++training.attempts;
    if (cloud_begin_request(CLOUD_HTTP_TRAIN_FRAME,"POST",path,"application/octet-stream",
          cloud->tof_payload,cloud->tof_payload_length,NULL,0U,1U)!=0) cloud_backoff();
    return 1;
  }
  if ((int32_t)(now-training.next_poll)>=0) {
    TOF_App_GetCaptureIdentity(boot);
    (void)snprintf(path,sizeof(path),"/api/device/training?boot=%s",boot[0]?boot:"00000000000000000000000000000000");
    training.next_poll=now+1000U;
    if (cloud_begin_request(CLOUD_HTTP_TRAIN_CONTROL,"GET",path,"application/json",NULL,0U,NULL,0U,1U)!=0) cloud_backoff();
    return 1;
  }
  return training.active?1:0;
}
#if defined(__GNUC__)
#pragma GCC pop_options
#endif
