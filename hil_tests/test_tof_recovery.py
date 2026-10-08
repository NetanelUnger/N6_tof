"""Execute the firmware's actual recovery functions with injected HAL failures.

No board or firmware writes. Requires Visual Studio C tools on Windows, or cc
on other hosts. The functions are extracted unchanged from tof_app.c; hardware
and ThreadX queue boundaries are mocked. This does not validate DMA registers.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source: str, name: str) -> str:
    match = re.search(r"^(?:static )?(?:void|uint32_t|TOF_StreamDestination_t|const char \*)\s*"
                      + re.escape(name) + r"\([^;]*?\)\s*\{", source, re.M)
    if not match:
        raise AssertionError(f"Definition not found: {name}")
    end = source.index("{", match.start())
    level = 1
    end += 1
    while level:
        level += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


PREFIX = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "tof_app.h"
#define TOF_RAW_SLOT_COUNT 3U
#define TOF_RECOVERY_MAX_ATTEMPTS 3U
#define TOF_RECOVERY_HEALTHY_FRAMES 30U
#define TOF_TARGET_FPS 10U
#define TOF_DEVICE_ID 0U
#define TOF_USECASE 0U
#define VL53L9_SYNC_AUTONOMOUS 1U
#define PLATFORM_GPIO_IT_EVT 1U
typedef struct { uint32_t id, generation; uint8_t data[14842]; } TOF_RawFrame_t;
typedef struct { int unused; } vl53l9_device_t;
typedef struct { uint32_t frame_period_us, sync; } vl53l9_profile_t;
static vl53l9_profile_t g_ranging_profiles[1];
static struct {
  struct { TOF_App_State_t state; } state;
  struct { int free_queue, ready_queue; TOF_RawFrame_t raw_frame_pool[3]; } buffers;
  struct { const char *error_stage; int error_code; uint32_t dropped_frames; } counters;
  struct { uint32_t requested, awaiting_frame, generation, attempts, successes,
    failures, consecutive_attempts, healthy_frames, last_tick;
    const char *stage; int error; } recovery;
} tof_context;
static int reset_calls, resets_to_fail, init_calls, inits_to_fail, start_calls;
static int release_calls, fatal_calls, change_request, ready_count;
static uint32_t tick;
static jmp_buf fatal_jump;
static UINT tx_interrupt_control(UINT mode) { (void)mode; return 0; }
static void tx_thread_sleep(ULONG ticks) { tick += (uint32_t)ticks; }
static uint32_t HAL_GetTick(void) { return ++tick; }
static void Debug_UART_Log(const char *tag, const char *fmt, ...) { (void)tag; (void)fmt; }
static int platform_recover_i3c(void) {
  ++reset_calls;
  if (resets_to_fail > 0) { --resets_to_fail; return -1; }
  return 0;
}
static UINT tx_queue_receive(int *queue, ULONG *message, ULONG wait) {
  (void)queue; (void)wait;
  if (ready_count) {
    --ready_count; *message = (ULONG)&tof_context.buffers.raw_frame_pool[1];
    return TX_SUCCESS;
  }
  return TX_QUEUE_EMPTY;
}
static UINT tx_queue_send(int *queue, ULONG *message, ULONG wait) {
  (void)queue; (void)message; (void)wait;
  /* A failed reset must never release a DMA destination. */
  assert(reset_calls > 0 && resets_to_fail == 0);
  ++release_calls; return TX_SUCCESS;
}
static void tof_log_queue_failure(const char *s, UINT u, const TOF_RawFrame_t *f)
  { (void)s; (void)u; (void)f; assert(0); }
static int platform_power_reset(uint8_t id) { (void)id; return 0; }
static int platform_assign_dynamic_address(void) { return 0; }
static int platform_acknowledge_event(int e) { (void)e; return 0; }
static int vl53l9_init(vl53l9_device_t *s) {
  (void)s; ++init_calls;
  if (inits_to_fail > 0) { --inits_to_fail; return -2; }
  return 0;
}
static int vl53l9_utils_set_profile(vl53l9_device_t *s, const vl53l9_profile_t *p) {
  (void)s; assert(p->frame_period_us == 100000 && p->sync == VL53L9_SYNC_AUTONOMOUS);
  if (change_request) {
    TOF_App_RequestStream(TOF_STREAM_BLE);
    TOF_App_SetPaused(1);
  }
  return 0;
}
static int vl53l9_start(vl53l9_device_t *s) { (void)s; ++start_calls; return 0; }
static void tof_fatal(const char *s, int e);
'''

TESTS = r'''
static void tof_fatal(const char *s, int e) {
  ++fatal_calls; tof_context.counters.error_stage = s;
  tof_context.counters.error_code = e; tof_context.state.state = TOF_APP_STATE_ERROR;
  tof_publication_blocked = 1; longjmp(fatal_jump, 1);
}
static void fresh(void) {
  memset(&tof_context, 0, sizeof(tof_context));
  memset((void *)&tof_desired, 0, sizeof(tof_desired));
  tof_context.state.state = TOF_APP_STATE_READY;
  tof_publication_blocked = 0; tof_stream_active = TOF_STREAM_NONE;
  reset_calls = resets_to_fail = init_calls = inits_to_fail = start_calls = 0;
  release_calls = fatal_calls = change_request = ready_count = 0;
  tof_desired.map_channel_mask = 0x15;
  tof_desired.processing_config.selected_filter = TOF_IMAGE_FILTER_MEDIAN;
}
int main(void) {
  vl53l9_device_t sensor = { 0 };
  TOF_DesiredState_t before;
  fresh();
  TOF_App_SetMapEnabled(1);
  TOF_App_RequestStream(TOF_STREAM_CLOUD);
  before = tof_desired;
  tof_request_recovery("status DMA completion", -1);
  assert(tof_context.state.state == TOF_APP_STATE_RECOVERING);
  assert(TOF_App_GetStreamDestination() == TOF_STREAM_NONE);
  assert(tof_recover(&sensor, &tof_context.buffers.raw_frame_pool[0]) == 1);
  assert(memcmp(&before, (const void *)&tof_desired, sizeof(before)) == 0);
  assert(release_calls == 1 && start_calls == 1);
  assert(tof_context.recovery.awaiting_frame == 1 && tof_context.recovery.successes == 0);
  puts("PASS running recovery retains destination/channels/filter; awaits fresh frame");
  tof_note_complete_acquisition();
  assert(tof_context.recovery.successes == 1 && tof_publication_blocked == 0);
  assert(tof_context.state.state == TOF_APP_STATE_READY);
  for (int i = 1; i < 29; ++i) tof_note_complete_acquisition();
  assert(tof_context.recovery.consecutive_attempts == 1);
  tof_note_complete_acquisition();
  assert(tof_context.recovery.consecutive_attempts == 0);
  puts("PASS first complete acquisition confirms recovery; only frame thirty replenishes budget");

  fresh();
  TOF_App_SetDatasetStreamEnabled(1); TOF_App_SetPaused(1);
  before = tof_desired;
  tof_request_recovery("stream pause", -1);
  assert(tof_recover(&sensor, NULL) == 0);
  assert(memcmp(&before, (const void *)&tof_desired, sizeof(before)) == 0);
  assert(start_calls == 0 && tof_context.state.state == TOF_APP_STATE_PAUSED);
  assert(tof_context.recovery.successes == 1);
  puts("PASS paused recovery retains binary dataset and does not start ranging");

  fresh();
  TOF_App_SetMapEnabled(1); TOF_App_RequestStream(TOF_STREAM_CLOUD);
  change_request = 1;
  tof_request_recovery("DSS DMA start", -1);
  assert(tof_recover(&sensor, NULL) == 0);
  assert(tof_desired.destination == TOF_STREAM_BLE && tof_desired.paused == 1);
  assert(start_calls == 0 && tof_context.recovery.successes == 1);
  puts("PASS latest command received during sensor initialization wins");

  fresh(); resets_to_fail = 1; ready_count = 1;
  tof_request_recovery("frame main DMA completion", -1);
  assert(tof_recover(&sensor, &tof_context.buffers.raw_frame_pool[0]) == 1);
  assert(reset_calls == 2 && release_calls == 2 && init_calls == 1);
  assert(tof_context.counters.dropped_frames == 1 && tof_context.recovery.failures == 1);
  puts("PASS failed DMA reset quarantines held slot; retry drains queued old frame");

  fresh(); inits_to_fail = 1;
  tof_request_recovery("DSS map command", -1);
  assert(tof_recover(&sensor, &tof_context.buffers.raw_frame_pool[0]) == 1);
  assert(reset_calls == 2 && release_calls == 1 && init_calls == 2);
  puts("PASS retry after sensor-init failure never releases a slot twice");

  fresh(); resets_to_fail = 99;
  tof_request_recovery("status DMA completion", -1);
  if (setjmp(fatal_jump) == 0) { (void)tof_recover(&sensor, &tof_context.buffers.raw_frame_pool[0]); assert(0); }
  assert(reset_calls == 3 && release_calls == 0 && fatal_calls == 1);
  assert(tof_context.recovery.failures == 3 && tof_publication_blocked == 1);
  puts("PASS persistent DMA failure exhausts exactly three attempts without slot reuse");

  fresh();
  for (int i = 0; i < 3; ++i) {
    tof_request_recovery("sensor interrupt timeout", -1);
    assert(tof_recover(&sensor, NULL) == 1);
  }
  tof_request_recovery("sensor interrupt timeout", -1);
  if (setjmp(fatal_jump) == 0) { (void)tof_recover(&sensor, NULL); assert(0); }
  assert(reset_calls == 3 && tof_context.recovery.successes == 0);
  puts("PASS a restart with no complete fresh frame cannot replenish the retry budget");

  fresh();
  TOF_RawFrame_t *frame = &tof_context.buffers.raw_frame_pool[0];
  frame->generation = 0;
  assert(tof_frame_is_current(frame) == 1);
  tof_context.recovery.generation = 1;
  assert(tof_frame_is_current(frame) == 0);
  frame->generation = 1;
  tof_publication_blocked = 1; assert(tof_frame_is_current(frame) == 0);
  tof_publication_blocked = 0; assert(tof_frame_is_current(frame) == 1);
  tof_context.state.state = TOF_APP_STATE_ERROR; assert(tof_frame_is_current(frame) == 0);
  puts("PASS old-generation/error/recovering frames cannot publish");

  fresh();
  TOF_App_SetMapEnabled(1); TOF_App_SetDatasetStreamEnabled(1);
  assert(tof_desired.map_enabled == 0 && tof_desired.dataset_stream_enabled == 1);
  TOF_App_ReleaseStream(TOF_STREAM_BLE);
  assert(tof_desired.destination == TOF_STREAM_USB);
  TOF_App_RequestStream(TOF_STREAM_CLOUD);
  TOF_App_RequestStream((TOF_StreamDestination_t)-1);
  assert(tof_desired.destination == TOF_STREAM_CLOUD);
  puts("PASS exclusive route and mutually exclusive USB map/dataset intent");
  return 0;
}
'''


def main() -> None:
    source = (ROOT / 'AppliNonSecure/Core/Src/tof_app.c').read_text(encoding='utf-8')
    start = source.index('typedef struct\n', source.index('/* Commands describe intent.'))
    end = source.index('void TOF_App_RequestStream', start)
    names = ['TOF_App_RequestStream', 'TOF_App_ReleaseStream',
             'TOF_App_GetStreamDestination', 'TOF_App_StreamName',
             'TOF_App_SetMapEnabled', 'TOF_App_SetDatasetStreamEnabled',
             'TOF_App_SetPaused', 'tof_release_raw_frame', 'tof_frame_is_current',
             'tof_request_recovery', 'tof_recover', 'tof_note_complete_acquisition']
    with tempfile.TemporaryDirectory(prefix='n6-tof-recovery-') as temp:
        folder = Path(temp)
        (folder / 'tx_api.h').write_text('''#include <stdint.h>
typedef unsigned UINT;
typedef uintptr_t ULONG;
#define TX_INT_DISABLE 1U
#define TX_TIMER_TICKS_PER_SECOND 100U
#define TX_SUCCESS 0U
#define TX_QUEUE_EMPTY 10U
#define TX_NO_WAIT 0U
''', encoding='utf-8')
        (folder / 'test.c').write_text(PREFIX + source[start:end]
            + '\n'.join(function(source, n) for n in names) + TESTS, encoding='utf-8')
        include = ROOT / 'AppliNonSecure/Core/Inc'
        if os.name == 'nt':
            vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
            vsroot = subprocess.check_output([str(vswhere), '-latest', '-products', '*',
                '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                '-property', 'installationPath'], text=True).strip()
            vcvars = Path(vsroot) / 'VC/Auxiliary/Build/vcvars64.bat'
            batch = folder / 'build.cmd'
            batch.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\n'
                f'cl /nologo /std:c11 /W3 /I"{folder}" /I"{include}" test.c /Fe:test.exe\n', encoding='utf-8')
            subprocess.run(['cmd.exe', '/d', '/c', str(batch)], cwd=folder, check=True)
            exe = folder / 'test.exe'
        else:
            compiler = shutil.which('cc')
            if not compiler:
                raise RuntimeError('A native C compiler is required')
            exe = folder / 'test'
            subprocess.run([compiler, '-std=c11', '-Wall', '-I', str(folder), '-I',
                            str(include), 'test.c', '-o', str(exe)], cwd=folder, check=True)
        subprocess.run([str(exe)], cwd=folder, check=True)


if __name__ == '__main__':
    main()
