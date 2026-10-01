#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Record what the vendor shipped, so drift becomes visible.

    python tools/qa/snapshot_vendor.py --repo ../aula-fseries-mn
    python tools/qa/snapshot_vendor.py --all

Writes <repo>/tools/vendor-baseline.json containing, per model:

  * the installer's SHA-256, size and download URL (from the portal's
    data/models.json where one is known),
  * the SHA-256 of the vendor's own English locale file,
  * that file's complete key -> English map.

Why this file exists
--------------------
Vendor installers and their extracted trees are gitignored: installers/,
.work/, .work2/ all hold vendor binaries and must never be committed.  That
means CI has no way to compare a shipped pack against the vendor's own key
set.  This baseline is the committed, text-only stand-in: it is the vendor's
key set without the vendor's binary.

Run this on a machine that has the installers, after every rebuild.
`vendor_drift.py` later re-downloads from the vendor and diffs against it.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localepack as lp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PORTAL = os.path.dirname(os.path.dirname(HERE))          # .../driver


def payload_kind(head):
    """What the vendor URL actually serves, from its magic bytes."""
    if head[:4] == b'Rar!':
        return 'rar'
    if head[:2] == b'PK':
        return 'zip'
    if head[:2] == b'MZ':
        return 'exe'
    if head[:5].lower() in (b'<!doc', b'<html'):
        return 'html'
    return 'other'


def fingerprint_url(url):
    """SHA-256 of exactly what the URL returns, whatever container it is.

    The installer .exe hash is NOT a usable drift signal on its own: the
    KYSONA M600 V2 download is a .rar that contains the .exe, so comparing the
    URL's bytes with our extracted .exe reports drift on every single run.
    Fingerprinting the URL payload itself is container-agnostic and correct.
    """
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    h = hashlib.sha256()
    size = 0
    head = b''
    with urllib.request.urlopen(req, timeout=180) as resp:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            if not head:
                head = chunk[:8]
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size, payload_kind(head)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


AULA_BASE = 'https://www.aulastar.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      'Chrome/120.0 Safari/537.36')


def portal_vendor_urls():
    """model-name -> vendor download URL.

    Primary source is the portal's data/models.json; tools/aula_links.json
    fills in models the portal does not list separately (F98pro V3 is only
    there).  Both files belong to the portal repo and are read, never written.
    """
    urls = {}

    links = os.path.join(PORTAL, 'tools', 'aula_links.json')
    if os.path.isfile(links):
        with io.open(links, encoding='utf-8') as fh:
            for name, href in json.load(fh).items():
                urls[name] = href if href.startswith('http') else AULA_BASE + href

    path = os.path.join(PORTAL, 'data', 'models.json')
    if os.path.isfile(path):
        with io.open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        for bucket in ('mongolian', 'others'):
            for m in data.get(bucket, []):
                if m.get('vendor'):
                    urls[m['name']] = m['vendor']
    return urls


def match_url(model_dir, urls):
    """'AULA_F98pro_V3_driver' -> the portal entry for 'F98pro V3'."""
    core = model_dir
    for pre in ('AULA_', 'KYSONA_'):
        if core.startswith(pre):
            core = core[len(pre):]
    for suf in ('_driver',):
        if core.endswith(suf):
            core = core[: -len(suf)]
    norm = lambda s: ''.join(ch for ch in s.lower() if ch.isalnum())
    want = norm(core)
    for name, url in urls.items():
        if norm(name) == want:
            return name, url
    return None, None


def widest_vendor_width(repo_root, family, model, kind, en_doc):
    """Per key, the widest the vendor's own locales render that string.

    Returns (list_of_widths_aligned_with_en_doc.entries, [locale names]).
    Only locale files with the vendor's exact key sequence are used, so the
    widths line up positionally and nothing is compared across shifted keys.
    """
    sibs = lp.sibling_locales(repo_root, family, model, kind)
    if not sibs:
        return None, []

    def occurrence_map(entries):
        """(key, nth occurrence of that key) -> value.

        Aligning on the key NAME plus its occurrence index, rather than on the
        whole sequence, is what makes this work: the vendor's own locale files
        are not parallel.  The F65 Chinese text.xml has 235 keys to English's
        231, and 1028.lan / 2052.lan simply omit the keys AULA never
        translated.  Demanding identical sequences threw all of that away and
        left English as the only comparator, which defeats the point.
        """
        seen, out = {}, {}
        for e in entries:
            n = seen.get(e.key, 0)
            seen[e.key] = n + 1
            out[(e.key, n)] = e.value
        return out

    en_index = []
    seen = {}
    for e in en_doc.entries:
        n = seen.get(e.key, 0)
        seen[e.key] = n + 1
        en_index.append((e.key, n))

    widths = [lp.display_width(e.value) for e in en_doc.entries]
    measured = []
    for name, path in sorted(sibs.items()):
        try:
            doc = lp.read(path, family)
        except Exception:                                     # noqa: BLE001
            continue
        other = occurrence_map(doc.entries)
        hits = 0
        for i, ident in enumerate(en_index):
            if ident not in other:
                continue
            hits += 1
            w = lp.display_width(other[ident])
            if w > widths[i]:
                widths[i] = w
        if hits >= len(en_index) // 2:     # a locale that covers half the keys
            measured.append('%s(%d)' % (name, hits))
    return widths, measured


def prev_record(previous, model, family):
    if not previous:
        return None
    models = previous.get('models', {})
    return models.get(model) or models.get('%s:%s' % (model, family))


def prev_installer(previous, model, family):
    rec = prev_record(previous, model, family)
    return (rec or {}).get('installer') or {}


def snapshot_repo(repo_root, urls, record_urls=False):
    kind = lp.repo_kind(repo_root)
    if kind is None:
        return None, 'not a recognised localisation repo'

    # Whatever is already recorded.  A snapshot run on a machine WITHOUT the
    # gitignored vendor trees must never blank out key sets that a previous run
    # captured - that would quietly disarm every CI check that depends on them.
    previous = None
    dest = os.path.join(repo_root, 'tools', 'vendor-baseline.json')
    if os.path.isfile(dest):
        try:
            with io.open(dest, encoding='utf-8') as fh:
                previous = json.load(fh)
        except ValueError:
            previous = None

    out = {
        '_note': 'Generated by driver/tools/qa/snapshot_vendor.py. '
                 'Vendor key sets recorded as text so CI can verify shipped '
                 'packs without the gitignored vendor binaries. Do not edit by hand.',
        'repo': kind,
        'generated': datetime.date.today().isoformat(),
        'models': {},
    }

    if kind == 'aula-driver-mn':
        # The vendor's own locales are committed here (it is a mirror), so the
        # baseline only needs the upstream fingerprint for drift detection.
        lang = os.path.join(repo_root, 'config', 'language.json')
        data, raw = lp.read_web_json_all(lang)
        upstream = {}
        for loc in data:
            if loc == 'mn':
                continue
            upstream.update({k: v for k, v in data[loc].items()})
        out['models']['web'] = {
            'family': 'web_json',
            'vendor_url': 'https://hed.aulacn.com/config/language.json',
            'vendor_file': {
                'path': 'config/language.json',
                'sha256': hashlib.sha256(raw).hexdigest(),
                'locales': sorted(k for k in data if k != 'mn'),
                'keys': len(upstream),
                'bare_lf': lp.bare_lf_count(raw, 'web_json'),
            },
            # The union of every upstream locale's keys.  Recorded separately
            # from 'english' because the two are NOT the same set: zh-cn
            # defines keyManu10, unit1 and unit2, which the en locale does not.
            # Diffing one against the other reports phantom drift.
            'upstream_keys': sorted(upstream),
            'english': [[k, v] for k, v in (data.get('en') or {}).items()],
            # Widest the vendor renders each key in any of its own 11 locales -
            # German and Turkish are the useful ones, they are the long ones.
            'vendor_width': [
                max([lp.display_width(data[loc][k])
                     for loc in data if loc != 'mn' and k in data[loc]] or [0])
                for k in (data.get('en') or {})
            ],
            'vendor_width_locales': sorted(k for k in data if k != 'mn'),
        }
        return out, None

    installers = os.path.join(repo_root, 'installers')
    missing_vendor = []
    carried_models = []

    for label, path, family in lp.shipped_artifacts(repo_root, kind):
        model = lp.model_of(label)
        en_path = lp.vendor_original(repo_root, family, model, kind)
        rec = {'family': family, 'artifact': label}

        exe = os.path.join(installers, model + '.exe')
        if os.path.isfile(exe):
            name, url = match_url(model, urls)
            rec['installer'] = {
                'name': os.path.basename(exe),
                'size': os.path.getsize(exe),
                'sha256': sha256(exe),
            }
            if url:
                rec['installer']['url'] = url
                rec['installer']['portal_name'] = name
                # NB: do not unpack into a name used by the enclosing loop.
                # An earlier version bound the payload kind to `kind`, which is
                # the REPO kind here, and every model after the first then
                # looked for its vendor original under a repo layout called
                # "exe" and silently recorded nothing.
                if record_urls:
                    try:
                        u_sha, u_size, u_kind = fingerprint_url(url)
                        rec['installer']['url_sha256'] = u_sha
                        rec['installer']['url_size'] = u_size
                        rec['installer']['url_kind'] = u_kind
                    except Exception as exc:                  # noqa: BLE001
                        rec['installer']['url_error'] = '%s: %s' % (type(exc).__name__, exc)
                elif prev_installer(previous, model, family):
                    # keep a fingerprint recorded by an earlier --record-urls run
                    old = prev_installer(previous, model, family)
                    for f in ('url_sha256', 'url_size', 'url_kind'):
                        if f in old:
                            rec['installer'][f] = old[f]

        if en_path:
            doc = lp.read(en_path, {'bycombo4': 'bycombo4', 'lan': 'lan',
                                    'kysona_xml': 'kysona_xml'}[family])
            rec['vendor_file'] = {
                'path': os.path.relpath(en_path, repo_root).replace('\\', '/'),
                'sha256': hashlib.sha256(doc.raw).hexdigest(),
                'keys': len(doc.entries),
                # The vendor embeds newlines inside a few message values.  Record
                # how many are bare LF in the vendor's own bytes so CI can tell a
                # faithful copy from line-ending drift introduced by our build.
                'bare_lf': lp.bare_lf_count(doc.raw, family),
            }
            # A LIST of pairs, not a dict: several families legitimately repeat a
            # key (44 <Item> under one <ComboBox>, KB.DIALOG/501 twice), so a dict
            # would silently collapse the vendor's own structure.
            rec['english'] = [[e.key, e.value] for e in doc.entries]

            # Width evidence.  For each key, the widest text the VENDOR itself
            # ships in any of its own locales.  That width shipped in production
            # software, so the control demonstrably holds it - which makes it a
            # far better yardstick for "will the Mongolian fit?" than English.
            widths, measured = widest_vendor_width(repo_root, family, model, kind, doc)
            if widths:
                rec['vendor_width'] = widths
                rec['vendor_width_locales'] = measured
        else:
            # No vendor tree here (CI, or a fresh clone).  Carry forward what a
            # previous run recorded rather than dropping it.
            old = prev_record(previous, model, family) or {}
            carried = [f for f in ('vendor_file', 'english', 'vendor_width',
                                   'vendor_width_locales') if f in old]
            for f in carried:
                rec[f] = old[f]
            if carried:
                rec['_carried_forward'] = True
                carried_models.append(model)
            else:
                missing_vendor.append(model)

        key = model if model not in out['models'] else '%s:%s' % (model, family)
        out['models'][key] = rec

    notes = []
    if carried_models:
        notes.append('kept previously recorded vendor data for: %s'
                     % ', '.join(carried_models))
    if missing_vendor:
        notes.append('NO vendor key set at all for: %s' % ', '.join(missing_vendor))
    return out, ('; '.join(notes) if notes else None)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', action='append', default=[],
                    help='repo checkout to snapshot (repeatable)')
    ap.add_argument('--all', action='store_true',
                    help='snapshot all three localisation repos found next to this one')
    ap.add_argument('--record-urls', action='store_true',
                    help='also download every vendor URL and record the SHA-256 of '
                         'what it serves. Needed before vendor_drift.py can compare '
                         'hashes: some downloads are .rar archives containing the '
                         '.exe, so the installer hash alone is not comparable.')
    ap.add_argument('--check', action='store_true',
                    help='do not write; report whether the committed baseline is stale')
    args = ap.parse_args()

    repos = list(args.repo)
    if args.all or not repos:
        for name in ('aula-driver-mn', 'aula-fseries-mn', 'kysona-m600-mn'):
            found = lp.find_sibling(name)
            if found:
                repos.append(found)

    urls = portal_vendor_urls()
    rc = 0
    for repo in repos:
        repo = os.path.abspath(repo)
        data, warn = snapshot_repo(repo, urls, args.record_urls)
        if data is None:
            print('%-20s SKIP  %s' % (os.path.basename(repo), warn))
            continue
        dest = os.path.join(repo, 'tools', 'vendor-baseline.json')
        blob = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False)

        old = None
        if os.path.isfile(dest):
            with io.open(dest, encoding='utf-8') as fh:
                old = fh.read()

        def strip_date(s):
            try:
                d = json.loads(s)
                d.pop('generated', None)
                return json.dumps(d, ensure_ascii=False, sort_keys=True)
            except Exception:
                return s

        same = old is not None and strip_date(old) == strip_date(blob)

        if args.check:
            print('%-20s %-8s %d model(s)%s'
                  % (data['repo'], 'CURRENT' if same else 'STALE',
                     len(data['models']), '  ' + warn if warn else ''))
            if not same:
                rc = 1
            continue

        if same:
            print('%-20s unchanged  (%d models)' % (data['repo'], len(data['models'])))
        else:
            with io.open(dest, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(blob + '\n')
            print('%-20s wrote tools/vendor-baseline.json  (%d models, %d KB)'
                  % (data['repo'], len(data['models']), len(blob) // 1024))
        if warn:
            print('%-20s   note: %s' % ('', warn))
    return rc


if __name__ == '__main__':
    sys.exit(main())
