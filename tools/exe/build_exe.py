#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the one-file Peaklab installers (.exe) with Inno Setup.

    python tools/exe/build_exe.py                 # every model
    python tools/exe/build_exe.py --only F65      # one model
    python tools/exe/build_exe.py --test          # TEST builds (no admin prompt) for tools/qa/test_exe_installers.ps1
    python tools/exe/build_exe.py --list

Needs, beside this repo (the folders the pack repos already use):
    aula-fseries-mn/installers/*.exe      the vendors' unmodified installers (gitignored)
    aula-fseries-mn/dist, dist-lan        the built language files
    kysona-m600-mn/installers, dist
and Inno Setup 6   (winget install JRSoftware.InnoSetup).

Output goes to <pack repo>/dist-exe/ - gitignored, because each exe embeds a
vendor installer. Release them as GitHub release assets, like the zips.
"""
import argparse
import glob
import hashlib
import io
import os
import subprocess
import sys
import uuid

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))      # folder holding all the repos
ISS = os.path.join(HERE, 'peaklab.iss')
VERSION = '1.6'

FS = os.path.join(ROOT, 'aula-fseries-mn')
KY = os.path.join(ROOT, 'kysona-m600-mn')

# (display name, key used in file names, family)
BYCOMBO4 = [('AULA F65', 'F65'), ('AULA F65 Pro', 'F65Pro'), ('AULA F75', 'F75'),
            ('AULA F99', 'F99'), ('AULA F99 Pro', 'F99Pro'), ('AULA F108', 'F108')]
LAN = [('AULA F75 MAX', 'F75MAX'), ('AULA F98 Pro', 'F98PRO'), ('AULA F98 Pro V3', 'F98pro_V3'),
       ('AULA F106 Pro', 'F106Pro'), ('AULA F108 Pro', 'F108Pro'), ('AULA F87 Wired', 'F87_Wired')]
KYSONA = [('KYSONA M600', 'M600'), ('KYSONA M600 V2', 'M600_V2')]


def models():
    out = []
    for name, key in BYCOMBO4:
        out.append(dict(family='bycombo4', name=name, key=key, repo=FS,
                        vendor=os.path.join(FS, 'installers', 'AULA_%s_driver.exe' % key),
                        lang=os.path.join(FS, 'dist', 'AULA_%s_driver' % key, 'text.xml'),
                        out='AULA_%s_driver_mn_setup' % key))
    for name, key in LAN:
        out.append(dict(family='lan', name=name, key=key, repo=FS,
                        vendor=os.path.join(FS, 'installers', 'AULA_%s_driver.exe' % key),
                        lang=os.path.join(FS, 'dist-lan', 'AULA_%s_driver' % key, 'app', 'language', '1104.lan'),
                        out='AULA_%s_driver_mn_setup' % key))
    for name, key in KYSONA:
        folder = os.path.join(KY, 'dist', 'KYSONA_%s_driver' % key)
        xmls = sorted(glob.glob(os.path.join(folder, '*.xml')))
        out.append(dict(family='kysona', name=name, key=key, repo=KY,
                        vendor=os.path.join(KY, 'installers', 'KYSONA_%s_driver.exe' % key),
                        lang=xmls[0] if xmls else os.path.join(folder, '(missing).xml'),
                        out='KYSONA_%s_driver_mn_setup' % key))
    return out


def find_iscc():
    cands = [os.environ.get('ISCC', '')]
    for base in (os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles(x86)', ''),
                 os.environ.get('ProgramFiles', ''), 'D:\\Program Files (x86)'):
        if base:
            cands.append(os.path.join(base, 'Programs', 'Inno Setup 6', 'ISCC.exe'))
            cands.append(os.path.join(base, 'Inno Setup 6', 'ISCC.exe'))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='build only this key, e.g. F65 or M600_V2')
    ap.add_argument('--test', action='store_true', help='TEST build: no admin prompt. Never ship it.')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--probe', action='store_true',
                    help='build the PROBE installers the search tests use (they look for a made-up filename)')
    ap.add_argument('--e2e', action='store_true',
                    help='build the END-TO-END test installer: embeds a harmless stand-in for the vendor installer, so the "driver is not installed yet" path can run')
    ap.add_argument('--dummy-vendor', action='store_true',
                    help='with --test: embed a 2-byte stand-in where the real vendor installer is missing (CI has none)')
    ap.add_argument('--sign', action='store_true',
                    help='Authenticode-sign the built exes with the certificate named by PEAKLAB_CERT_THUMBPRINT (see sign_exe.ps1)')
    ap.add_argument('--allow-untrusted', action='store_true',
                    help='with --sign: accept a certificate Windows does not trust (self-signed). Pipeline test only - never publish')
    ap.add_argument('--no-timestamp', action='store_true', help='with --sign: skip the timestamp (tests only)')
    ap.add_argument('--out', help='output folder (default: <pack repo>/dist-exe, or dist-exe-test with --test)')
    args = ap.parse_args()

    todo = [m for m in models() if not args.only or m['key'].lower() == args.only.lower()]
    if args.list:
        for m in todo:
            print('%-9s %-18s %s' % (m['family'], m['name'], m['out']))
        return 0
    if not todo:
        sys.exit('no model matches %r' % args.only)

    iscc = find_iscc()
    if not iscc:
        sys.exit('Inno Setup 6 not found. Install it:  winget install JRSoftware.InnoSetup  (or set ISCC=...)')
    print('compiler: %s%s\n' % (iscc, '   [TEST BUILDS]' if args.test else ''))

    if args.dummy_vendor and not args.test:
        sys.exit('--dummy-vendor is for test builds only: a real build must embed the real vendor installer')

    def compile_one(m, outdir, outname, extra=()):
        guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'peaklab.mn/' + outname)).upper()
        cmd = [iscc, '/Q', '/DFAMILY=%s' % m['family'], '/DMODEL=%s' % m['name'],
               '/DVENDOR=%s' % m['vendor'], '/DLANGSRC=%s' % m['lang'], '/DOUTDIR=%s' % outdir,
               '/DOUTNAME=%s' % outname, '/DVERSION=%s' % VERSION, '/DAPPGUID=%s' % guid]
        if args.test:
            cmd.append('/DTESTBUILD=1')
        cmd.extend(extra)
        cmd.append(ISS)
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        exe = os.path.join(outdir, outname + '.exe')
        if r.returncode != 0 or not os.path.isfile(exe):
            print('FAIL  %-18s\n%s' % (m['name'], (r.stdout + r.stderr).strip()[-1500:]))
            return None
        return exe

    stand_in = None
    if args.dummy_vendor:
        import tempfile
        stand_in = os.path.join(tempfile.mkdtemp(prefix='peaklab-vendor-'), 'vendor_installer.exe')
        with open(stand_in, 'wb') as fh:
            fh.write(b'MZ')

    pick = lambda key: [m for m in models() if m['key'] == key][0]

    if args.e2e:
        # The commonest customer case: the driver is NOT installed, so the exe must run the
        # vendor's installer and then carry on. Test builds never run the real one, so here
        # the "vendor" is a small Inno installer of our own that drops a stand-in driver into
        # a sandbox folder (PEAKLAB_FAKE_DIR) and registers it, as AULA's installer does.
        if not args.test:
            sys.exit('--e2e implies --test')
        import tempfile
        CR, LF = chr(13), chr(10)
        src = tempfile.mkdtemp(prefix='peaklab-fakevendor-')
        with open(os.path.join(src, 'PeaklabProbe.exe'), 'wb') as fh:
            fh.write(b'MZ stand-in driver')
        cfg = ('[OPT]' + CR + LF + 'Title=AULA F65' + CR + LF + 'Appdir=BYCOMBO4' + CR + LF + CR + LF +
               'Lang1=English,en' + CR + LF + 'Lang2=' + chr(0x7B80) + chr(0x4F53) + chr(0x4E2D) + chr(0x6587) + ',sc' + CR + LF + CR + LF)
        with open(os.path.join(src, 'Cfg.ini'), 'wb') as fh:
            fh.write(bytes([0xFF, 0xFE]) + cfg.encode('utf-16-le'))
        outdir = args.out or os.path.join(FS, 'dist-exe-test')
        os.makedirs(outdir, exist_ok=True)
        r = subprocess.run([iscc, '/Q', '/DSRCDIR=%s' % src, '/DOUTDIR=%s' % outdir,
                            os.path.join(HERE, 'fake_vendor.iss')],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        fake = os.path.join(outdir, 'fake_vendor.exe')
        if r.returncode != 0 or not os.path.isfile(fake):
            print('FAIL  fake vendor' + LF + (r.stdout + r.stderr).strip()[-1500:])
            return 1
        m = dict(pick('F65'))
        m['vendor'] = fake
        exe = compile_one(m, outdir, 'E2E_bycombo4',
                          ['/DTESTRUNVENDOR=1', '/DVENDORARGS=/VERYSILENT', '/DTESTMASK=PeaklabProbe.exe'])
        if not exe:
            return 1
        print('built E2E_bycombo4     %5.1f MB  %s' % (os.path.getsize(exe) / 1048576.0, os.path.relpath(exe, ROOT)))
        return 0

    if args.probe:
        # A made-up driver name, so a search test cannot find (and patch) a REAL driver
        # installed on this very PC. Only the family's logic is under test.
        if not args.test:
            sys.exit('--probe implies --test')
        outdir = args.out or os.path.join(FS, 'dist-exe-test')
        os.makedirs(outdir, exist_ok=True)
        done = 0
        for m, name, mask in ((pick('F65'), 'PROBE_bycombo4', 'PeaklabProbe.exe'),
                              (pick('F106Pro'), 'PROBE_lan', 'PeaklabLan.exe'),
                              (pick('M600'), 'PROBE_kysona', 'PeaklabMouse*.exe')):
            mm = dict(m)
            if not os.path.isfile(mm['vendor']):
                if not stand_in:
                    print('SKIP  %s: vendor installer missing (use --dummy-vendor)' % name)
                    continue
                mm['vendor'] = stand_in
            exe = compile_one(mm, outdir, name, ['/DTESTMASK=%s' % mask])
            if not exe:
                return 1
            done += 1
            print('built %-18s %5.1f MB  %s' % (name, os.path.getsize(exe) / 1048576.0, os.path.relpath(exe, ROOT)))
        print('\nbuilt %d probe installer(s)' % done)
        return 0

    built, skipped = [], []
    for m in todo:
        mm = dict(m)
        if stand_in and not os.path.isfile(mm['vendor']):
            mm['vendor'] = stand_in
        missing = [p for p in (mm['vendor'], mm['lang']) if not os.path.isfile(p)]
        if missing:
            skipped.append((m['name'], missing))
            print('SKIP  %-18s missing: %s' % (m['name'], ', '.join(os.path.relpath(p, ROOT) for p in missing)))
            continue
        outdir = args.out or os.path.join(m['repo'], 'dist-exe-test' if args.test else 'dist-exe')
        os.makedirs(outdir, exist_ok=True)
        exe = compile_one(mm, outdir, m['out'])
        if not exe:
            return 1
        built.append((mm, exe))
        print('built %-18s %5.1f MB  %s' % (m['name'], os.path.getsize(exe) / 1048576.0, os.path.relpath(exe, ROOT)))

    print('\nbuilt %d, skipped %d' % (len(built), len(skipped)))

    if args.sign:
        if not built:
            sys.exit('nothing to sign')
        if args.test and not args.allow_untrusted:
            sys.exit('--sign on a TEST build is only for proving the pipeline: add --allow-untrusted')
        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'sign_exe.ps1'),
               '-Files', ','.join(exe for _, exe in built)]
        if args.allow_untrusted:
            cmd.append('-AllowUntrusted')
        if args.no_timestamp:
            cmd.append('-NoTimestamp')
        print('\nsigning:')
        if subprocess.run(cmd).returncode != 0:
            print('\nSIGNING FAILED - do not publish these files.')
            return 1
        if args.allow_untrusted:
            print('\nNOTE: --allow-untrusted. Windows does NOT trust that signature. Do not publish these files.')

    if built:
        print('\nSHA-256 of the vendor installer embedded in each (also written to the exe\'s setup log):')
        for m, exe in built:
            print('  %-18s %s' % (m['name'], sha(m['vendor'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
