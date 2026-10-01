#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Has the vendor shipped a driver update that our language pack no longer fits?

    python tools/qa/vendor_drift.py --web            # no download, fast
    python tools/qa/vendor_drift.py --repo ../kysona-m600-mn
    python tools/qa/vendor_drift.py --all            # downloads ~120 MB
    python tools/qa/vendor_drift.py --all --hash-only

This is the notification that turns a silent failure into a known one.  A
vendor ships an update, their key set moves, our pack stops matching, and
today nobody finds out until a Mongolian customer opens a half-English UI.

Two levels, because they cost very different amounts
----------------------------------------------------
  hash level   HEAD/GET the installer and compare its SHA-256 and size with
               tools/vendor-baseline.json.  Cheap.  Answers "did anything
               change at all", which is the question that matters most.

  key level    extract the changed installer with innoextract, read its own
               English locale file, and report exactly which keys are new,
               removed, or now carry different English.  Needs innoextract
               and is only attempted for installers whose hash moved.

The web driver needs neither: hed.aulacn.com serves config/language.json
directly, so --web is a plain HTTP GET and a key diff, and is the one mode
that runs happily in CI.

Exit codes: 0 nothing moved, 1 drift found, 2 could not check.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localepack as lp  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      'Chrome/120.0 Safari/537.36')
WEB_LANG_URL = 'https://hed.aulacn.com/config/language.json'
TIMEOUT = 120


def fetch(url, dest=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if dest is None:
            return resp.read(), dict(resp.headers)
        h = hashlib.sha256()
        size = 0
        with open(dest, 'wb') as fh:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                size += len(chunk)
        return h.hexdigest(), size


def payload_kind(head):
    if head[:4] == b'Rar!':
        return 'rar'
    if head[:2] == b'PK':
        return 'zip'
    if head[:2] == b'MZ':
        return 'exe'
    if head[:5].lower() in (b'<!doc', b'<html'):
        return 'html'
    return 'other'


def load_baseline(repo_root):
    p = os.path.join(repo_root, 'tools', 'vendor-baseline.json')
    if not os.path.isfile(p):
        return None
    with io.open(p, encoding='utf-8') as fh:
        return json.load(fh)


def diff_pairs(old_pairs, new_pairs, label_old='baseline', label_new='vendor'):
    """Report added / removed / changed-English keys between two key->text lists."""
    def first_map(pairs):
        out = {}
        for k, v in pairs:
            out.setdefault(k, v)
        return out

    old, new = first_map(old_pairs), first_map(new_pairs)
    added = [k for k in new if k not in old]
    removed = [k for k in old if k not in new]
    changed = [(k, old[k], new[k]) for k in new
               if k in old and str(old[k]).strip() != str(new[k]).strip()]
    return added, removed, changed


def report_diff(name, added, removed, changed, verbose):
    if not (added or removed or changed):
        print('   %-28s key set unchanged' % name)
        return False
    print('   %-28s DRIFT' % name)
    if added:
        print('      %d NEW key(s) with no Mongolian text yet: %s'
              % (len(added), ', '.join(sorted(added)[:10])))
    if removed:
        print('      %d key(s) the vendor removed: %s'
              % (len(removed), ', '.join(sorted(removed)[:10])))
    if changed:
        print('      %d key(s) whose English changed - the Mongolian may now be wrong:'
              % len(changed))
        for k, a, b in sorted(changed)[:(None if verbose else 8)]:
            print('        %-22s %r' % (k, a[:52]))
            print('        %-22s %r' % ('', b[:52]))
    return True


# --------------------------------------------------------------------------

def check_web(repo_root, verbose):
    """AULA's web driver: the locale file is fetchable, no installer involved."""
    baseline = load_baseline(repo_root)
    if not baseline or 'web' not in baseline.get('models', {}):
        print('   no baseline for the web driver - run snapshot_vendor.py')
        return 2
    rec = baseline['models']['web']
    print('\n== aula-driver-mn (web driver)')
    print('   GET %s' % WEB_LANG_URL)
    try:
        raw, _hdrs = fetch(WEB_LANG_URL)
    except (urllib.error.URLError, OSError) as exc:
        print('   could not reach the vendor: %s' % exc)
        return 2

    # Our local copy is the vendor file with our mn locale merged in and
    # re-indented, so its hash never equals the vendor's.  Printed for the
    # record; the key diff below is what actually decides.
    print('   remote sha256 %s  (%d bytes)' % (hashlib.sha256(raw).hexdigest()[:16], len(raw)))

    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except ValueError as exc:
        print('   vendor file did not parse as JSON: %s' % exc)
        return 2

    # Compare like with like.  'english' is the vendor's en locale;
    # 'upstream_keys' is the union over every upstream locale.  They differ -
    # zh-cn carries keyManu10, unit1 and unit2 and en does not - so diffing one
    # against the other invents drift that is not there.
    remote_en = sorted((data.get('en') or {}).items())
    _a, _r, changed = diff_pairs(rec.get('english') or [], remote_en)

    remote_union = set()
    for loc in data:
        if loc != 'mn':
            remote_union |= set(data[loc])
    known = set(rec.get('upstream_keys') or [k for k, _ in (rec.get('english') or [])])
    added = sorted(remote_union - known)
    removed = sorted(known - remote_union)

    drifted = report_diff('config/language.json', added, removed, changed, verbose)

    # which of the new keys have no Mongolian at all
    if added:
        mnfile = os.path.join(repo_root, 'tools', 'mn.json')
        if os.path.isfile(mnfile):
            strings, _meta = lp.load_translation_source(mnfile)
            untranslated = [k for k in added if k not in strings]
            if untranslated:
                print('      of those, %d are absent from tools/mn.json: %s'
                      % (len(untranslated), ', '.join(sorted(untranslated)[:10])))
    new_locales = sorted(set(data) - set((rec.get('vendor_file') or {}).get('locales') or []) - {'mn'})
    if new_locales:
        print('      vendor added locale(s): %s' % ', '.join(new_locales))
        drifted = True
    return 1 if drifted else 0


def find_innoextract():
    exe = shutil.which('innoextract')
    if exe:
        return exe
    base = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages')
    if os.path.isdir(base):
        for dirpath, _d, files in os.walk(base):
            if 'innoextract.exe' in files:
                return os.path.join(dirpath, 'innoextract.exe')
    return None


VENDOR_LOCALE_PATH = {
    'bycombo4':   ('app', 'Text', 'en', 'text.xml'),
    'lan':        ('app', 'language', '1033.lan'),
    'kysona_xml': ('app', 'Language', '0-English.xml'),
}


def check_installers(repo_root, hash_only, verbose, only=None):
    baseline = load_baseline(repo_root)
    kind = lp.repo_kind(repo_root)
    if not baseline:
        print('   no tools/vendor-baseline.json - run snapshot_vendor.py first')
        return 2
    print('\n== %s' % kind)

    inno = None if hash_only else find_innoextract()
    if not hash_only and not inno:
        print('   innoextract not found - falling back to hash-only')
        hash_only = True

    drifted = unreachable = 0
    tmp = tempfile.mkdtemp(prefix='drift-')
    try:
        for model, rec in sorted(baseline['models'].items()):
            if only and only.lower() not in model.lower():
                continue
            inst = rec.get('installer') or {}
            url = inst.get('url')
            if not url:
                print('   %-28s no vendor URL recorded - cannot check' % model)
                unreachable += 1
                continue

            dest = os.path.join(tmp, model + '.bin')
            try:
                digest, size = fetch(url, dest)
            except (urllib.error.URLError, OSError) as exc:
                print('   %-28s download failed: %s' % (model, exc))
                unreachable += 1
                continue

            head = open(dest, 'rb').read(8)
            kind = payload_kind(head)

            # Compare against the fingerprint of what the URL SERVES, not
            # against our extracted .exe.  The KYSONA M600 V2 download is a
            # .rar containing the installer, so the .exe hash never matches the
            # download and a naive comparison cries drift on every run.
            known = inst.get('url_sha256')
            if not known:
                print('   %-28s no URL fingerprint recorded - cannot compare. '
                      'Run: snapshot_vendor.py --record-urls' % model)
                unreachable += 1
                continue

            if digest == known:
                print('   %-28s unchanged  (%s, %.1f MB, %s)'
                      % (model, digest[:12], size / 1e6, kind))
                continue

            drifted += 1
            print('   %-28s VENDOR DOWNLOAD CHANGED' % model)
            print('      was %s  %s bytes  (%s)'
                  % (known[:16], inst.get('url_size'), inst.get('url_kind', '?')))
            print('      now %s  %d bytes  (%s)' % (digest[:16], size, kind))

            if hash_only:
                continue
            if kind != 'exe':
                print('      the vendor serves a .%s here, not the installer itself - '
                      'unpack it by hand and re-run snapshot_vendor.py' % kind)
                continue

            work = os.path.join(tmp, model + '.x')
            res = subprocess.run([inno, '--extract', '--output-dir', work,
                                  '--silent', dest],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0:
                print('      could not extract it - compare by hand')
                continue
            rel = VENDOR_LOCALE_PATH.get(rec.get('family'))
            path = os.path.join(work, *rel) if rel else None
            if not path or not os.path.isfile(path):
                print('      new build has no %s - the driver family may have changed'
                      % ('/'.join(rel) if rel else '?'))
                continue
            try:
                doc = lp.read(path, rec['family'])
            except Exception as exc:                          # noqa: BLE001
                print('      new locale file did not parse: %s' % exc)
                continue
            added, removed, changed = diff_pairs(rec.get('english') or [],
                                                 [(e.key, e.value) for e in doc.entries])
            report_diff('  ' + model, added, removed, changed, verbose)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if unreachable:
        print('   %d model(s) could not be checked' % unreachable)
    return 1 if drifted else (2 if unreachable else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', action='append', default=[])
    ap.add_argument('--web', action='store_true',
                    help='check only the web driver (no downloads, CI-friendly)')
    ap.add_argument('--all', action='store_true',
                    help='check every repo including the installer downloads')
    ap.add_argument('--hash-only', action='store_true',
                    help='compare installer hashes, do not extract')
    ap.add_argument('--model', help='limit to models whose name contains this')
    ap.add_argument('--verbose', '-v', action='store_true')
    args = ap.parse_args()

    rc = 0
    if args.web or (not args.repo and not args.all):
        repo = lp.find_sibling('aula-driver-mn')
        if not repo:
            print('aula-driver-mn not found next to this checkout')
            return 2
        rc = max(rc, check_web(repo, args.verbose))
        if args.web:
            print('\n%s' % ('VENDOR DRIFT' if rc == 1 else
                            'no drift' if rc == 0 else 'COULD NOT CHECK'))
            return rc

    repos = list(args.repo)
    if args.all:
        for name in ('aula-fseries-mn', 'kysona-m600-mn'):
            found = lp.find_sibling(name)
            if found:
                repos.append(found)

    for repo in repos:
        repo = os.path.abspath(repo)
        if lp.repo_kind(repo) == 'aula-driver-mn':
            rc = max(rc, check_web(repo, args.verbose))
        else:
            rc = max(rc, check_installers(repo, args.hash_only, args.verbose, args.model))

    print('\n%s' % ('VENDOR DRIFT - a pack may no longer match its driver' if rc == 1
                    else 'no drift' if rc == 0 else 'COULD NOT CHECK EVERYTHING'))
    return rc


if __name__ == '__main__':
    sys.exit(main())
