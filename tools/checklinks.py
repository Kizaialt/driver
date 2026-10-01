#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check every URL in data/models.json actually resolves.

    python tools/checklinks.py

Vendor download links are the fragile part of this page - AULA's are
token-bearing query strings that could rot - so this is worth re-running
before any deploy.

Two vendor behaviours used to be reported as rot, and were not:

  * aulastar.com rate-limits a burst of parallel requests, so three of the
    F-series download tokens came back 000 purely because they were asked
    for at the same moment as nine others. Anything that fails the parallel
    pass is therefore re-probed on its own, slowly, before it is believed.

  * the aulacn.com online drivers answer curl with 403 no matter what,
    including hed.aulacn.com - the very host the Peaklab web driver is
    mirrored from, which demonstrably works in a browser. A 403/405/429 is
    a door closed to scripts, not a dead link, so it is reported in its own
    bucket instead of failing the run.

A checker that cries wolf gets ignored, and then a genuinely dead download
ships. Hence the two buckets.
"""
import io
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'models.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'

OK = ('200', '206')
# A server that is up and answering, but refusing this particular client.
BOT_BLOCKED = ('401', '403', '405', '429')

# ...but only AULA's online drivers are known to do that to curl. A 403 from
# anywhere else - our own GitHub release assets, the token-bearing installer
# downloads - means a deleted release or a revoked token, which is exactly the
# rot this script exists to catch, so it must still fail the run.
BOT_BLOCK_HOSTS = ('.aulacn.com', '.aulastar.com')


def may_block_scripts(label, url):
    host = urlparse(url).hostname or ''
    return label.endswith('[web]') and host.endswith(BOT_BLOCK_HOSTS)


def probe(url):
    """HEAD first; some hosts only answer GET, so fall back to a ranged GET."""
    try:
        out = subprocess.run(
            ['curl', '-sSI', '-L', '-m', '30', '-A', UA, '-o', os.devnull,
             '-w', '%{http_code}', url],
            capture_output=True, text=True, timeout=60)
        code = (out.stdout or '').strip()[-3:]
        if code in ('200', '206'):
            return code
        out = subprocess.run(
            ['curl', '-sS', '-L', '-m', '40', '-r', '0-2048', '-A', UA,
             '-o', os.devnull, '-w', '%{http_code}', url],
            capture_output=True, text=True, timeout=70)
        return (out.stdout or '').strip()[-3:] or '000'
    except Exception as exc:
        return 'ERR ' + type(exc).__name__


def main():
    with io.open(DATA, encoding='utf-8') as fh:
        data = json.load(fh)

    targets = []
    for m in data['mongolian']:
        for field in ('web', 'auto', 'vendor', 'pack', 'vendor_page'):
            if m.get(field):
                targets.append(('%s %s [%s]' % (m['brand'], m['name'], field), m[field]))
    for o in data['others']:
        if o.get('vendor'):
            targets.append(('%s [%s]' % (o['name'], o['how']), o['vendor']))
    for name, url in data.get('links', {}).items():
        targets.append(('links.%s' % name, url))

    # de-duplicate identical URLs, keep one representative label
    seen = {}
    for label, url in targets:
        seen.setdefault(url, label)
    unique = [(label, url) for url, label in seen.items()]
    print('checking %d unique URLs (%d references)\n' % (len(unique), len(targets)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(lambda t: probe(t[1]), unique))

    # Second opinion, one at a time. aulastar.com hands out 000 to whichever
    # requests arrive together, so a failure in the parallel pass means very
    # little until it has been asked again on its own.
    retried = [i for i, c in enumerate(codes) if c not in OK]
    if retried:
        print('re-probing %d slowly before believing them...\n' % len(retried))
        for i in retried:
            time.sleep(1.5)
            codes[i] = probe(unique[i][1])

    bad, blocked = [], []
    for (label, url), code in zip(unique, codes):
        if code in OK:
            mark = ''
        elif code in BOT_BLOCKED and may_block_scripts(label, url):
            blocked.append((label, url, code))
            mark = '  (script-blocked)'
        else:
            bad.append((label, url, code))
            mark = '  <-- BROKEN'
        print('  %-4s %-34s %s%s' % (code, label[:34], url[:58], mark))

    print()
    if blocked:
        print('%d reachable but closed to scripts - check these in a real '
              'browser, do not assume rot:' % len(blocked))
        for label, url, code in blocked:
            print('  %s  %s  %s' % (code, label, url))
        print()
    if bad:
        print('%d BROKEN:' % len(bad))
        for label, url, code in bad:
            print('  %s  %s  %s' % (code, label, url))
        return 1
    print('all %d URLs reachable (%d of them only via a real browser)'
          % (len(unique), len(blocked)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
