"""Prepare reviewable candidate files only; do not edit or build product firmware."""
from pathlib import Path
import difflib, hashlib, json
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=Path(__file__).parent/'evidence/st67-cp10-transport-candidate'
STAGE=OUT/'candidate'
OUT.mkdir(exist_ok=False)
changed={}
def edit(path, replacements):
    original=(ROOT/path).read_text()
    candidate=original
    for old,new in replacements:
        assert candidate.count(old)==1,(path,old,candidate.count(old))
        candidate=candidate.replace(old,new)
    changed[path]=(original,candidate)
    target=STAGE/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(candidate,newline='\n')

spi='ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.c'
edit(spi,[
 ('#define SPI_XFER_TRANSPORT_ERROR        (-3)', '#define SPI_XFER_TRANSPORT_ERROR        (-3)\n\n/** Peer framing cannot establish a safe transaction boundary. */\n#define SPI_XFER_PROTOCOL_ERROR         (-4)'),
 ('  int32_t initialized;','  int32_t initialized;\n  /** Sticky ambiguity; cleared only by proven transport teardown. */\n  volatile int32_t transport_fault;'),
 ('    SPI_STAT_INC(&engine->stat, hdr_err, 1U);\n    goto out;', '    SPI_STAT_INC(&engine->stat, hdr_err, 1U);\n    err = SPI_XFER_PROTOCOL_ERROR;\n    goto out;'),
 ('out:\n  /* A timed-out DMA', 'out:\n  /* Bytes may already have reached the NCP. Local DMA cleanup cannot prove\n   * rejection or restore the peer parser boundary. Stop before any replay;\n   * retain TX ownership for the existing coordinated teardown. */\n  engine->transport_fault = err;\n  engine->stop = 1;\n  /* A timed-out DMA'),
 ('        int32_t ready_after_failure = spi_port_is_ready();', '''        /* spi_xfer_one has already completed or retained DMA cleanup. A\n         * sticky transport/protocol fault cannot retry now or on a later RDY\n         * event, including an RX-only failure or a malformed peer header. */\n        if (engine->transport_fault != 0) break;\n        int32_t ready_after_failure = spi_port_is_ready();'''),
 ('''        if (xfer_status == SPI_XFER_TRANSPORT_ERROR)
        {
          /* A timed-out DMA leaves HAL_SPI busy, so another transfer would
           * fail immediately. Abort only the local peripheral/DMA state after
           * CS is low; the NCP is not reset and the owned TX buffer is kept. */
          if (spi_port_abort() == 0)
          {
            SPI_STAT_INC(&engine->stat, transport_recoveries, 1U);
          }
          else
          {
            spi_err("failed to abort incomplete local spi transaction\\n");
          }
        }
''',''),
 ('''        /* A polling/DMA failure can leave SPI_RDY high with no future edge.
         * Retry the same owned buffer while the NCP still requests service.
         * If a TX buffer is retained, a low level is also safe: the next
         * spi_xfer_one() performs its normal bounded ready wait. */''','''        /* Only pre-transfer failure reaches this path: no RX allocation or
         * no ready handshake. No command bytes were sent, so retaining and
         * retrying this TX is safe. Explicit peer rx_stall uses the separate
         * successful-transaction path above and remains unchanged. */'''),
 ('int32_t spi_transaction_init(void)\n{\n  int32_t ret;', '''int32_t spi_transaction_faulted(void)
{
  return xfer_engine.transport_fault;
}

int32_t spi_transaction_init(void)
{
  int32_t ret;
  /* Fault recovery must quiesce/deinit first, never clear the fence in place. */
  if (xfer_engine.transport_fault != 0) return -1;'''),
 ('''int32_t spi_read(struct spi_msg *msg, int32_t timeout_ms)
{''','''int32_t spi_read(struct spi_msg *msg, int32_t timeout_ms)
{
  if ((xfer_engine.transport_fault != 0) || (xfer_engine.stop != 0)) return -6;'''),
 ('''int32_t spi_write(struct spi_msg *msg, int32_t timeout_ms)
{''','''int32_t spi_write(struct spi_msg *msg, int32_t timeout_ms)
{
  /* -6 is a hard lifecycle/fence error, never the zero-byte BUSY codes. */
  if ((xfer_engine.transport_fault != 0) || (xfer_engine.stop != 0)) return -6;'''),
])
header='ThirdParty/ST67W6X_Network_Driver/Driver/W61_bus/spi_iface.h'
edit(header,[('int32_t spi_transaction_init(void);', '''/** Sticky transport/protocol fault; only successful deinit clears it. */
int32_t spi_transaction_faulted(void);

int32_t spi_transaction_init(void);''')])
common='ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c'
edit(common,[
 ('''  bool notification = (mdm->notify_phase != 0U) &&''','''  if (spi_transaction_faulted() != 0)
  {
    mdm->handler_data.tx_desynchronized = true;
    return -EIO;
  }
  bool notification = (mdm->notify_phase != 0U) &&'''),
 ('''  *bytes_read = 0U;
  if (mdm->spi_rx_pending == NULL)''','''  *bytes_read = 0U;
  if (spi_transaction_faulted() != 0)
  {
    mdm->handler_data.tx_desynchronized = true;
    /* Retained packet tail belongs to teardown; do not feed a later parser.
     * The parser must yield while the existing recovery owner quiesces it. */
    vTaskDelay(1U);
    return -EIO;
  }
  if (mdm->spi_rx_pending == NULL)'''),
])
radio='AppliNonSecure/Core/Src/wifi_ble_app.c'
edit(radio,[
 ('''    struct modem_cmd_handler_data *handler = &driver->Modem.handler_data;
    if (handler->tx_desynchronized''','''    struct modem_cmd_handler_data *handler = &driver->Modem.handler_data;
    if (spi_transaction_faulted() != 0) handler->tx_desynchronized = true;
    if (handler->tx_desynchronized'''),
 ('''    const char *reason = driver->Modem.handler_data.tx_desynchronized ? "AT_FENCED" :''','''    const char *reason = spi_transaction_faulted() != 0 ? "SPI_FENCED" :
        driver->Modem.handler_data.tx_desynchronized ? "AT_FENCED" :'''),
 ('''  } else if (driver->Modem.handler_data.tx_desynchronized) {
    status->state''','''  } else if (spi_transaction_faulted() != 0) {
    status->state = WIFI_BLE_SERVICE_FAULT; status->reason = "SPI_FENCED";
  } else if (driver->Modem.handler_data.tx_desynchronized) {
    status->state''')
])
# Unmodified dependency needed by actual-C fixture extraction.
config='ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_default_config.h'
dest=STAGE/config;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/config).read_bytes())
patch=''.join(''.join(difflib.unified_diff(a.splitlines(keepends=True),b.splitlines(keepends=True),fromfile='a/'+p,tofile='b/'+p)) for p,(a,b) in changed.items())
(OUT/'PROPOSED-NOT-APPLIED-spi-fence.patch').write_text(patch,newline='\n')
(OUT/'candidate-manifest.json').write_text(json.dumps([{'path':p,'original_sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256((STAGE/p).read_bytes()).hexdigest()} for p in changed],indent=2)+'\n')
print('Prepared four-file isolated candidate. Production source unchanged. No firmware build, package or hardware.')
