#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check every URL in data/models.json actually resolves.

    python tools/checklinks.py

Vendor download links are the fragile part of this page - AULA's are
token-bearing query strings that could rot - so this is worth re-running
before any deploy.
"""
import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'models.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'


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

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda t: probe(t[1]), unique))

    bad = []
    for (label, url), code in zip(unique, codes):
        ok = code in ('200', '206')
        if not ok:
            bad.append((label, url, code))
        print('  %-4s %-34s %s' % (code, label[:34], url[:64]))

    print()
    if bad:
        print('%d BROKEN:' % len(bad))
        for label, url, code in bad:
            print('  %s  %s  %s' % (code, label, url))
        return 1
    print('all %d URLs reachable' % len(unique))
    return 0


if __name__ == '__main__':
    sys.exit(main())
