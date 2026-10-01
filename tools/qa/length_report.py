#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Where is the Mongolian text likely to overflow its control?

    python tools/qa/length_report.py                 # worst 40, all repos
    python tools/qa/length_report.py --top 100
    python tools/qa/length_report.py --repo ../kysona-m600-mn
    python tools/qa/length_report.py --csv overflow.csv
    python tools/qa/length_report.py --vs-english    # the weaker ranking

Nothing in these packs has ever been opened on real hardware, so whether a
string fits is genuinely unknown.  This is the closest we can get without a
keyboard on the desk.

The yardstick is NOT English
----------------------------
English is a poor reference: it is one of the most compact languages in the
set, so measuring against it flags half the file and tells you nothing about
which half matters.

The vendor ships its own translations of the same UI - German, Russian,
Korean, Chinese, Turkish, Arabic depending on the model.  Every one of those
strings SHIPPED.  A control that already holds AULA's own German or Russian
text demonstrably holds that width in production software.  So the question
worth asking is:

    does our Mongolian string exceed the widest text the vendor itself
    put in that same control?

Rows where it does are the ones to look at, longest overhang first.  Rows
where it does not are almost certainly fine and are not printed.

Width, not character count: 设置 is two characters and as wide as four Latin
ones, so East Asian Wide and Fullwidth characters count double.  Cyrillic
counts single - which is exactly why a Mongolian string can look short and
still be wider than the Chinese the control was sized around.

Vendor widths come from tools/vendor-baseline.json, so this runs in CI too.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localepack as lp  # noqa: E402

# A control holding this much or less is a button, tab, column header or list
# item: no room to grow, and an overflowing label is clipped rather than
# wrapped.  Above it, the string is a message in a dialog that wraps.
TIGHT = 28


def rows_for_repo(repo_root):
    """(model, key, english, mongolian, mn_w, vendor_w, locales) per string."""
    kind = lp.repo_kind(repo_root)
    out = []
    if kind is None or kind == 'driver':
        return kind, out

    bpath = os.path.join(repo_root, 'tools', 'vendor-baseline.json')
    if not os.path.isfile(bpath):
        return kind, out
    with io.open(bpath, encoding='utf-8') as fh:
        baseline = json.load(fh)

    if kind == 'aula-driver-mn':
        rec = baseline['models']['web']
        data, _raw = lp.read_web_json_all(os.path.join(repo_root, 'config', 'language.json'))
        mn = data.get('mn', {})
        widths = rec.get('vendor_width') or []
        locales = ','.join(rec.get('vendor_width_locales') or [])
        for i, (k, en) in enumerate(rec['english']):
            v = mn.get(k)
            if not isinstance(v, str) or not v.strip():
                continue
            vw = widths[i] if i < len(widths) else lp.display_width(en)
            out.append(('web', k, en, v, lp.display_width(v), vw, locales))
        return kind, out

    for label, path, family in lp.shipped_artifacts(repo_root, kind):
        model = lp.model_of(label)
        rec = (baseline['models'].get(model)
               or baseline['models'].get('%s:%s' % (model, family)))
        if not rec or not isinstance(rec.get('english'), list):
            continue
        ours = lp.read(path, family).entries
        if len(ours) != len(rec['english']):
            continue
        widths = rec.get('vendor_width') or []
        locales = ','.join(rec.get('vendor_width_locales') or [])
        short = model.replace('AULA_', '').replace('KYSONA_', '').replace('_driver', '')
        for i, ((k, en), entry) in enumerate(zip(rec['english'], ours)):
            v = entry.value
            if not isinstance(v, str) or not v.strip() or not str(en).strip():
                continue
            if not lp.CYRILLIC.search(v):
                continue                    # deliberately still English
            vw = widths[i] if i < len(widths) else lp.display_width(en)
            out.append((short, k.split('/')[-1], en, v, lp.display_width(v), vw, locales))
    return kind, out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', action='append', default=[])
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--csv')
    ap.add_argument('--vs-english', action='store_true',
                    help='rank by the Mongolian/English ratio instead (weaker)')
    args = ap.parse_args()

    repos = list(args.repo)
    if not repos:
        for name in ('aula-driver-mn', 'aula-fseries-mn', 'kysona-m600-mn'):
            found = lp.find_sibling(name)
            if found:
                repos.append(found)

    # dedupe: the same string ships on six models, it is one problem
    merged = {}
    per_repo = defaultdict(lambda: [0, 0])
    locales_seen = {}
    for repo in repos:
        kind, rows = rows_for_repo(os.path.abspath(repo))
        if not rows:
            continue
        for model, key, en, mn, mw, vw, locales in rows:
            per_repo[kind][0] += 1
            if mw > vw:
                per_repo[kind][1] += 1
            locales_seen[kind] = locales
            sig = (kind, en, mn)
            if sig in merged:
                merged[sig][0].add(model)
                merged[sig][1].add(key)
                merged[sig][3] = max(merged[sig][3], vw)
            else:
                merged[sig] = [{model}, {key}, mw, vw]

    rows = []
    for (kind, en, mn), (models, keys, mw, vw) in merged.items():
        ew = lp.display_width(en)
        rows.append({
            'repo': kind,
            'models': ','.join(sorted(models)),
            'key': ','.join(sorted(keys)[:2]),
            'english': en,
            'mongolian': mn,
            'mn_w': mw,
            'vendor_w': vw,
            'en_w': ew,
            'excess': mw - vw,
            'ratio_vs_vendor': round(mw / vw, 2) if vw else 0,
            'ratio_vs_english': round(mw / ew, 2) if ew else 0,
            'control': 'tight' if vw <= TIGHT else 'message',
        })

    if args.csv:
        with io.open(args.csv, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in sorted(rows, key=lambda r: -r['excess']):
                w.writerow(r)
        print('wrote %s  (%d rows)' % (args.csv, len(rows)))

    print('String-length overflow report')
    print('=' * 100)
    for kind, (total, over) in sorted(per_repo.items()):
        print('  %-18s %4d translated strings, %3d wider than any locale the vendor ships '
              '(%.0f%%)' % (kind, total, over, 100.0 * over / total if total else 0))
        print('  %-18s vendor comparison locales: %s' % ('', locales_seen.get(kind, '-')))
    print()

    if args.vs_english:
        key = lambda r: -r['ratio_vs_english']
        title = 'Widest against ENGLISH (weaker signal - English is compact)'
        risky = [r for r in rows if r['ratio_vs_english'] > 1.0]
    else:
        key = lambda r: (-r['excess'], -r['ratio_vs_vendor'])
        title = ('Wider than ANY locale the vendor ships for the same control '
                 '- these are the overflow candidates')
        risky = [r for r in rows if r['excess'] > 0]

    tight = [r for r in risky if r['control'] == 'tight']
    msg = [r for r in risky if r['control'] != 'tight']

    def table(label, items, n):
        print('-' * 100)
        print('%s  (%d)' % (label, len(items)))
        print('-' * 100)
        print('%-9s %-19s %4s %4s %4s  %-30s %s'
              % ('repo', 'models', 'mn', 'ven', '+', 'English', 'Mongolian'))
        for r in sorted(items, key=key)[:n]:
            print('%-9s %-19s %4d %4d %+4d  %-30s %s'
                  % (r['repo'].replace('-mn', '').replace('aula-', '').replace('kysona-', ''),
                     r['models'][:19], r['mn_w'], r['vendor_w'], r['excess'],
                     r['english'][:30], r['mongolian'][:44]))
        if len(items) > n:
            print('   ... %d more' % (len(items) - n))

    print(title)
    table('TIGHT CONTROLS - button/tab/column/list item, clipped not wrapped '
          '(vendor width <= %d)' % TIGHT, tight, args.top)
    print()
    table('DIALOG MESSAGES - these wrap, so overhang is usually survivable',
          msg, max(8, args.top // 4))

    print()
    print('%d of %d distinct strings exceed the vendor\'s own widest text; '
          '%d of those are in tight controls.'
          % (len(risky), len(rows), len(tight)))
    print('Nothing here is a confirmed defect: it is a ranked list of what to '
          'look at first when a keyboard is available.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
