"""Actual documented list parser: complete inventory, bounded borrowed output."""
from test_fs_read_lifetime import PREFIX
from test_wifi_scan_lifetime import ROOT,run_native
from test_wifi_assoc_admission import extract_function
from test_raw_send_response import extract

EXTRA = r'''
#define W61_SYS_FS_MAX_FILES 32
#define W61_SYS_FS_FILENAME_SIZE 32
typedef struct {char filename[32][32];uint32_t nb_files;} W61_FS_FilesList_t;
static volatile uint32_t fs_list_header_seen,fs_list_invalid;
#define MODEM_CMD_DEFINE(n) MODEM_CMD_DIRECT_DEFINE(n)
#define MODEM_CMD(s,f,n,d) {s}
'''
STUB = r'''
static void line(struct modem_cmd_handler_data*d,char*s){char*args[]={s};
 assert(on_cmd_fs_listfiles(d,0,args,1)==0 && !critical);}
static int32_t modem_cmd_send_ext(unsigned*i,void*h,struct modem_cmd*c,unsigned n,const uint8_t*t,unsigned sem,unsigned timeout,unsigned flags){
 struct modem_cmd_handler_data*d=((struct {void*cmd_handler_data;}*)h)->cmd_handler_data;
 struct modem*m=d->user_data;assert(m->rx_data && n==1 && timeout==2000 && !critical);
 assert(flags==(MODEM_NO_TX_LOCK|MODEM_TX_TRACK_RAW_WRITE));
 if(mode==1)return W61_STATUS_TIMEOUT;
 d->raw_command_attempted=true;
 if(mode==2)return W61_STATUS_TIMEOUT;
 if(mode==3)return W61_STATUS_ERROR;
 if(mode==4)return W61_STATUS_OK; /* bare OK cannot prove absence */
 if(mode==5)line(d,"n6settings0.cfg"); /* missing header */
 else line(d,"+FS:LIST");
 if(mode==6)line(d,"+FS:LIST"); /* duplicate header */
 line(d,".");line(d,"..");
 if(mode==8){line(d,"abcdefghijklmnopqrstuvwxyz0123456789");}
 else if(mode==9 || mode==11){for(unsigned j=0;j<(mode==9?33U:32U);++j){char name[32];snprintf(name,sizeof name,"synthetic%02u",j);line(d,name);}}
 else if(mode!=10){line(d,"n6settings0.cfg");line(d,"n6cloud.cfg");}
 return W61_STATUS_OK;
}
'''
TESTS = r'''
int main(void){
 struct modem_cmd_handler_data d={0};W61_Object_t o={0};W61_FS_FilesList_t list;
 o.Modem.handler.cmd_handler_data=&d;d.user_data=&o.Modem;d.sem_tx_lock=1;
 for(mode=0;mode<=11;++mode){memset(&list,0xa5,sizeof list);d.tx_desynchronized=false;releases=0;
  unsigned r=W61_FS_ListFiles(&o,&list);assert(!critical && !o.Modem.rx_data);
  assert(releases==(mode==7?0:1));assert(d.tx_desynchronized==(mode==2));
  if(mode==0){assert(r==W61_STATUS_OK && list.nb_files==2);assert(!strcmp(list.filename[0],"n6settings0.cfg"));}
  else if(mode==11)assert(r==W61_STATUS_OK && list.nb_files==32);
  else if(mode==10)assert(r==W61_STATUS_OK && !list.nb_files);
  else assert(r!=W61_STATUS_OK);
  W61_FS_FilesList_t returned=list;unsigned header=fs_list_header_seen,bad=fs_list_invalid;
  line(&d,"late-file");assert(!memcmp(&list,&returned,sizeof list) && fs_list_header_seen==header && fs_list_invalid==bad);
 }
 puts("PASS actual list retires output before unlock; late callbacks cannot write or mutate inventory evidence");
 puts("PASS documented header+filenames+OK, empty inventory, duplicate/missing header, long filename/overflow, prewrite/true timeout");
 return 0;
}
'''
def main():
    source=(ROOT/'ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_sys.c').read_text()
    callback=extract(source,'on_cmd_fs_listfiles',True)
    run_native(PREFIX+EXTRA+callback+STUB+extract_function(source,'W61_FS_ListFiles')+TESTS)
if __name__=='__main__':main()
