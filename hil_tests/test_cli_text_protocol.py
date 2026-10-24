"""Host-only completion compatibility, never opens hardware."""
from cli_text_protocol import reply_results, reply_finished, reply_succeeded

text = b'first\rsecond\r\rn6> \n'
for i in range(len(text)):
    assert not reply_finished(text[:i])
assert reply_succeeded(text)
assert reply_results(text + b'rejected\rFAIL\r\n') == ['complete', 'failed']
assert reply_finished(b'FAIL\n') and not reply_succeeded(b'FAIL\n')
assert not reply_finished(b'legacy line\r\n')
assert reply_succeeded(b'first\rsecond\r\r\n')
assert reply_succeeded(b'[CLI-RESULT] state=accepted\r\nbody\r\n[CLI-RESULT] state=complete\r\n')
assert not reply_finished(b'\x06\n')
print('PASS host final LF, CR multiline fragments, visible FAIL, raw controls and legacy completion')
