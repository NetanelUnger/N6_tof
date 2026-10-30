from pathlib import Path
import hashlib, difflib
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=Path(__file__).resolve().parent/'evidence/st67-cp5-20261028'
p=ROOT/'hil_tests/test_cloud_request_budget.py'
raw=p.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='4ce4757542e3c53ab785e41262f474eb61baf3fbcf5e84526718f4a970853b9a'
old=raw.decode(); s=old
s=s.replace('#define TOF_STREAM_CLOUD 3U', '#define TOF_STREAM_CLOUD 3U\n#define TOF_IMAGE_TRAINING_N6DF 4U')
s=s.replace('static unsigned tick,close_failed,close_calls,releases,receives,starts;',
'''static unsigned tick,close_failed,close_calls,releases,receives,starts,training_ticks;
static struct {unsigned active,failures;} training;
static void cloud_training_tick(void){++training_ticks;}''')
s=s.replace('int socket; struct {unsigned enabled,backoff_seconds,tof_frames_dropped,state;} status;',
'''int socket; struct {unsigned enabled,backoff_seconds,tof_frames_dropped,state;} status;
 struct {unsigned mode;} tof_info;''')
s=s.replace(' puts("PASS loss of IP leaves Cloud waiting while enabled/pairing intent is preserved");',
''' puts("PASS loss of IP leaves Cloud waiting while enabled/pairing intent is preserved");
 unsigned before_ticks=training_ticks;
 training.active=1;cloud->tof_info.mode=TOF_IMAGE_TRAINING_N6DF;
 cloud->tof_pending=1;cloud_network_epoch++;
 cloud_process(1);assert(training.failures==1 && !cloud->tof_pending);
 cloud_process(1);assert(training.failures==1 && training_ticks==before_ticks+2);
 puts("PASS network epoch retires a pending training frame exactly once while training receives every worker tick");
 cloud->tof_pending=1;cloud->tof_info.mode=0;cloud_network_epoch++;
 cloud_process(1);assert(training.failures==1);
 training.active=0;cloud->tof_pending=1;cloud->tof_info.mode=TOF_IMAGE_TRAINING_N6DF;cloud_network_epoch++;
 cloud_process(1);assert(training.failures==1);
 puts("PASS ordinary image and inactive training do not add a false training failure");
 before_ticks=training_ticks;cloud=NULL;cloud_process(1);assert(training_ticks==before_ticks);''')
assert s!=old and s.count('static void cloud_training_tick')==1
# The fixture's mode constant must follow the imported production enum.
import re
header=(ROOT/'AppliNonSecure/Core/Inc/tof_image_codec.h').read_text()
value=re.search(r'^#define TOF_IMAGE_TRAINING_N6DF\s+(\d+)U',header,re.M)
if value:
    s=s.replace('#define TOF_IMAGE_TRAINING_N6DF 4U','#define TOF_IMAGE_TRAINING_N6DF '+value[1]+'U')
else:
    raise RuntimeError('Inspect actual training mode enum before updating this fixture')
(OUT/'test_cloud_request_budget.before.py.txt').write_bytes(raw)
p.write_text(s,encoding='utf-8',newline='')
(OUT/'cloud-budget-fixture.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='a/hil_tests/test_cloud_request_budget.py',tofile='b/hil_tests/test_cloud_request_budget.py')),encoding='utf-8')
print('updated only cloud budget host fixture; original and diff retained')
