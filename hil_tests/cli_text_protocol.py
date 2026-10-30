"""Remote CLI CR lines / final LF, with legacy marker compatibility."""
import re


def reply_results(text):
    if isinstance(text, (bytes, bytearray)):
        text = text.decode('utf-8', 'replace')
    results = []
    start = 0
    for match in re.finditer('\n', text):
        part = text[start:match.start()]
        start = match.end()
        lines = [line.strip() for line in part.split('\r') if line.strip()]
        last = lines[-1] if lines else ''
        legacy = re.fullmatch(r'(?:n6>\s*)?\[CLI-RESULT\] state=(accepted|complete|rejected|failed)(?: reason=\w+)?', last)
        if legacy:
            results.append(legacy[1])
        elif last == 'FAIL':
            results.append('failed')
        elif (not part.endswith('\r') or '\r' in part[:-1]) and not any(c in part for c in '\x06\x15\x18'):
            results.append('complete')
    return results


def reply_finished(text):
    results = reply_results(text)
    return bool(results and results[-1] in ('complete', 'failed', 'rejected'))


def reply_succeeded(text):
    results = reply_results(text)
    return bool(results and results[-1] == 'complete')
