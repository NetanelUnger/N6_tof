"""Host-only UART capture shutdown tests; never open a hardware port."""
import unittest
from types import SimpleNamespace
from run_xip_ota_capture import stop_reader

class CaptureShutdownTests(unittest.TestCase):
    def test_stop_precedes_join_and_file_close(self):
        events=[]
        stop=SimpleNamespace(set=lambda:events.append('stop'))
        reader=SimpleNamespace(join=lambda **kw:events.append('join'),is_alive=lambda:False)
        result={}
        stop_reader(stop,reader,None,result)
        events.append('close files')
        self.assertEqual(events,['stop','join','close files'])
        self.assertTrue(result['reader_stopped'])

    def test_pending_read_is_cancelled_before_final_join(self):
        events=[];alive=[True]
        def cancel():events.append('cancel');alive[0]=False
        stop=SimpleNamespace(set=lambda:events.append('stop'))
        reader=SimpleNamespace(join=lambda **kw:events.append('join'),is_alive=lambda:alive[0])
        result={}
        stop_reader(stop,reader,SimpleNamespace(cancel_read=cancel),result)
        self.assertEqual(events,['stop','join','cancel','join'])
        self.assertTrue(result['reader_stopped'])

    def test_stuck_reader_fails_instead_of_claiming_clean_capture(self):
        result={}
        with self.assertRaisesRegex(RuntimeError,'did not stop'):
            stop_reader(SimpleNamespace(set=lambda:None),
                SimpleNamespace(join=lambda **kw:None,is_alive=lambda:True),
                SimpleNamespace(cancel_read=lambda:None),result)
        self.assertFalse(result['reader_stopped'])

if __name__=='__main__':unittest.main()
