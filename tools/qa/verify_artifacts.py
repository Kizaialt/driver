#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prove every shipped locale artifact is correct, in all three pack repos.

    python tools/qa/verify_artifacts.py                 # all repos found nearby
    python tools/qa/verify_artifacts.py --repo ../aula-fseries-mn
    python tools/qa/verify_artifacts.py --verbose
    python tools/qa/verify_artifacts.py --self-test     # feed it broken input

What it checks, per artifact
----------------------------
  parses                the file loads with the reader its family requires
  encoding              BOM and line endings match the vendor's own dialect
  no metadata           no "_"-prefixed key reached the file, and no value is
                        a non-string (the apply-mn.js bug: an ARRAY landed in
                        config/language.json where getI18n expects a string)
  no duplicate keys     including JSON duplicates, which json.load silently eats
  key set               identical to the vendor's own English file - no missing
                        key (blank label in the UI) and no extra key
  no empty values       every key whose English is non-empty has Mongolian text
  numbers survive       purely numeric / unit values are byte-identical
  Mongolian present     a sanity floor on Cyrillic coverage
  family extras         Cfg.ini lists "Монгол,mn"; config.xml lists 1104;
                        KYSONA ComboBoxName control ids are untouched
  zip matches           every dist/*.zip holds exactly the loose files beside it

Where the reference comes from
------------------------------
The vendor's English original lives under .work/ and .work2/, which are
gitignored because they are extracted vendor binaries.  So:

  locally  - the vendor original is used directly when present,
  in CI    - tools/vendor-baseline.json (committed, text only) stands in.

Both are reported, so you can see which one a run used.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localepack as lp  # noqa: E402

CYR = lp.CYRILLIC

# Values the vendor itself leaves in English or that are not words at all.
# Kept deliberately short: this list suppresses noise, it must not suppress bugs.
KYSONA_NEVER_TRANSLATE = {'ComboBoxName'}


class Report(object):
    def __init__(self):
        self.fail = []
        self.warn = []
        self.checked = 0

    def error(self, where, msg):
        self.fail.append((where, msg))

    def warning(self, where, msg):
        self.warn.append((where, msg))

    @property
    def ok(self):
        return not self.fail


# --------------------------------------------------------------------------
# reference resolution
# --------------------------------------------------------------------------

def load_baseline(repo_root):
    path = os.path.join(repo_root, 'tools', 'vendor-baseline.json')
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding='utf-8') as fh:
        return json.load(fh)


class Reference(object):
    """The vendor's own English file, as an ORDERED list of (key, value).

    Ordered, not a dict: three of the four families legitimately repeat a key
    (44 <Item> under one <ComboBox>, KB.DIALOG/501 twice, tc_yun1 twice on the
    F75).  A dict would collapse the vendor's own structure and the comparison
    would stop meaning anything.
    """

    def __init__(self, pairs, source, bare_lf=None):
        self.pairs = [(k, v) for k, v in pairs]
        self.source = source
        self.bare_lf = bare_lf

    @property
    def keys(self):
        return [k for k, _ in self.pairs]


def baseline_record(baseline, model, family):
    if not baseline:
        return None
    models = baseline.get('models', {})
    return models.get(model) or models.get('%s:%s' % (model, family))


def reference_for(repo_root, kind, label, family, baseline):
    """Return (Reference, description) or (None, why_not)."""
    model = lp.model_of(label)

    if kind == 'aula-driver-mn':
        data, _raw = lp.read_web_json_all(os.path.join(repo_root, 'config', 'language.json'))
        # Every key any upstream locale defines must exist in mn, or getI18n()
        # returns '' and the label renders blank.  en carries the English text.
        upstream = {}
        for loc in data:
            if loc == 'mn':
                continue
            for k, v in data[loc].items():
                upstream.setdefault(k, v)
        for k, v in (data.get('en') or {}).items():
            upstream[k] = v
        src = 'config/language.json (upstream locales, in repo)'
        return Reference(sorted(upstream.items()), src), src

    local = lp.vendor_original(repo_root, family, model, kind)
    if local:
        doc = lp.read(local, family)
        src = os.path.relpath(local, repo_root).replace('\\', '/') + ' (vendor original)'
        return Reference([(e.key, e.value) for e in doc.entries], src,
                         lp.bare_lf_count(doc.raw, family)), src

    rec = baseline_record(baseline, model, family)
    if rec and 'english' in rec:
        pairs = rec['english']
        if isinstance(pairs, dict):                    # older baseline shape
            pairs = list(pairs.items())
        src = 'tools/vendor-baseline.json'
        return Reference([(k, v) for k, v in pairs], src,
                         (rec.get('vendor_file') or {}).get('bare_lf')), src

    return None, 'no vendor original and no baseline entry'


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_duplicate_json_keys(raw):
    """json.load keeps the last of duplicated keys and says nothing."""
    dupes = []

    def hook(pairs):
        seen = Counter(k for k, _ in pairs)
        dupes.extend(k for k, n in seen.items() if n > 1)
        return dict(pairs)

    json.loads(raw.decode('utf-8-sig'), object_pairs_hook=hook)
    return dupes


def check_artifact(rep, repo_root, kind, label, path, family, baseline, verbose):
    where = '%s :: %s' % (kind, label)
    rep.checked += 1

    raw = open(path, 'rb').read()

    # --- encoding contract -------------------------------------------------
    for msg in lp.encoding_problems(raw, family):
        rep.error(where, msg)

    # --- parse -------------------------------------------------------------
    try:
        doc = lp.read(path, family)
    except Exception as exc:                                  # noqa: BLE001
        rep.error(where, 'does not parse: %s: %s' % (type(exc).__name__, exc))
        return
    entries = doc.entries

    if family == 'web_json':
        for k in check_duplicate_json_keys(raw):
            rep.error(where, 'duplicate JSON key %r (json.load silently keeps the last)' % k)

    # --- metadata leakage --------------------------------------------------
    leaked = [e.key for e in entries if e.key.split('/')[-1].startswith('_')]
    if leaked:
        rep.error(where, '%d "_"-prefixed metadata key(s) reached the shipped file: %s'
                  % (len(leaked), ', '.join(leaked[:6])))

    nonstr = [(e.key, type(e.value).__name__) for e in entries
              if not isinstance(e.value, str)]
    if nonstr:
        rep.error(where, '%d value(s) are not strings: %s'
                  % (len(nonstr), ', '.join('%s=%s' % kv for kv in nonstr[:6])))
        entries = [e for e in entries if isinstance(e.value, str)]

    # --- key sequence vs the vendor ---------------------------------------
    ref, src = reference_for(repo_root, kind, label, family, baseline)
    if ref is None:
        rep.warning(where, 'key set NOT verified - %s' % src)
        aligned = []
    else:
        ours_keys = [e.key for e in entries]
        ref_keys = ref.keys

        ordered = family in lp.ORDERED_FAMILIES
        if ours_keys == ref_keys:
            aligned = list(zip(ref.pairs, entries))
        elif not ordered and Counter(ours_keys) == Counter(ref_keys):
            by_key = dict(ref.pairs)
            aligned = [((e.key, by_key[e.key]), e) for e in entries]
        else:
            aligned = []
            ours_count = Counter(ours_keys)
            ref_count = Counter(ref_keys)
            missing = [k for k in ref_count if ours_count[k] < ref_count[k]]
            extra = [k for k in ours_count if ref_count[k] < ours_count[k]]
            if missing:
                rep.error(where, '%d key(s) the vendor defines are missing or under-counted '
                                 '(blank UI label): %s'
                          % (len(missing), ', '.join(sorted(missing)[:8])))
            if extra:
                rep.error(where, '%d key(s) the vendor does not define: %s'
                          % (len(extra), ', '.join(sorted(extra)[:8])))
            if not missing and not extra and ordered:
                first = next((i for i, (a, b) in enumerate(zip(ref_keys, ours_keys)) if a != b), 0)
                rep.error(where, 'same keys but a different order - the app reads this file '
                                 'positionally; first differs at index %d: vendor %r, ours %r'
                          % (first, ref_keys[first], ours_keys[first]))
            # still line up what we can, by key, for the value checks
            by_key = {}
            for k, v in ref.pairs:
                by_key.setdefault(k, v)
            aligned = [((e.key, by_key[e.key]), e) for e in entries if e.key in by_key]

        # --- line-ending dialect vs the vendor's own bytes -------------------
        if ref.bare_lf is not None:
            ours_lf = lp.bare_lf_count(raw, family)
            if ours_lf > ref.bare_lf:
                rep.error(where, 'line-ending drift: %d bare LF where the vendor file has %d '
                                 '- this family ships CRLF throughout, including inside values'
                          % (ours_lf, ref.bare_lf))

        # --- empty values ---------------------------------------------------
        empty = [e.key for (_k, en), e in aligned
                 if isinstance(e.value, str) and not e.value.strip() and str(en).strip()]
        if empty:
            rep.error(where, '%d key(s) are blank where the vendor has text: %s'
                      % (len(empty), ', '.join(sorted(set(empty))[:8])))

        # --- numeric / unit values must survive ------------------------------
        drifted = []
        for (_k, en), e in aligned:
            if not isinstance(e.value, str) or not isinstance(en, str) or not en.strip():
                continue
            if lp.NUMERIC_ONLY.match(en.strip()) and e.value.strip() != en.strip():
                drifted.append('%s: %r -> %r' % (e.key, en, e.value))
        if drifted:
            rep.error(where, '%d numeric/unit value(s) changed: %s'
                      % (len(drifted), '; '.join(drifted[:4])))

        # --- one key, two meanings, one translation --------------------------
        # tools/mn.json for the BYCOMBO4 family is keyed by the vendor's key
        # name, so a key that carries two DIFFERENT English strings inside the
        # same model gets one Mongolian string for both - and one of the two
        # labels is then simply wrong.  _overrides ("key|English") exists to
        # resolve this; the check finds the places where one is still needed.
        if family == 'bycombo4':
            groups = defaultdict(list)
            for (k, en), e in aligned:
                groups[k].append((en, e.value))
            for k, vals in groups.items():
                english_set = {en.strip() for en, _ in vals if str(en).strip()}
                if len(english_set) < 2:
                    continue
                if len({mn for _en, mn in vals}) > 1:
                    continue                    # already disambiguated
                a, b = sorted(english_set, key=len)[0], sorted(english_set, key=len)[-1]
                nested = a.lower() in b.lower()
                detail = ('%s: %s  ->  one Mongolian string %r for both'
                          % (k, ' / '.join(repr(x)[:46] for x in sorted(english_set)),
                             vals[0][1][:40]))
                if nested:
                    rep.warning(where, 'one key, two English spellings, one translation '
                                       '(they mean the same thing): %s' % detail)
                else:
                    rep.error(where, 'one key carries two DIFFERENT English strings and got '
                                     'the same Mongolian for both - one label is wrong. Add an '
                                     '_overrides entry keyed "%s|<English>". %s'
                              % (k.split('/')[-1], detail))

        # --- control identifiers (KYSONA) ------------------------------------
        if family == 'kysona_xml':
            bad = ['%s: %r -> %r' % (e.key, en, e.value)
                   for (_k, en), e in aligned
                   if e.key.split('/')[-1] in KYSONA_NEVER_TRANSLATE and e.value != en]
            if bad:
                rep.error(where, '%d ComboBoxName control id(s) were translated: %s'
                          % (len(bad), '; '.join(bad[:4])))

    # --- Mongolian actually present ---------------------------------------
    translatable = [e for e in entries
                    if isinstance(e.value, str) and e.value.strip()
                    and not lp.NUMERIC_ONLY.match(e.value.strip())]
    cyr = sum(1 for e in translatable if CYR.search(e.value))
    if translatable:
        ratio = cyr / float(len(translatable))
        if ratio < 0.5:
            rep.error(where, 'only %d/%d translatable values contain Cyrillic (%.0f%%) '
                             '- this does not look like a Mongolian file'
                      % (cyr, len(translatable), ratio * 100))
        elif ratio < 0.75:
            rep.warning(where, 'only %d/%d translatable values contain Cyrillic (%.0f%%)'
                        % (cyr, len(translatable), ratio * 100))

    if verbose:
        print('    %-46s %4d keys   ref: %s' % (label, len(entries), src))


def check_family_extras(rep, repo_root, kind, verbose):
    """Cfg.ini / config.xml - the files that make the locale selectable."""
    j = lambda *p: os.path.join(repo_root, *p)

    if kind == 'aula-fseries-mn':
        dist = j('dist')
        if os.path.isdir(dist):
            for model in sorted(os.listdir(dist)):
                cfg = os.path.join(dist, model, 'reference', 'app', 'Cfg.ini')
                if not os.path.isdir(os.path.join(dist, model)):
                    continue
                where = '%s :: dist/%s' % (kind, model)
                if not os.path.isfile(cfg):
                    rep.error(where, 'reference/app/Cfg.ini missing - the pack cannot '
                                     'show Mongolian in the language list')
                    continue
                raw = open(cfg, 'rb').read()
                for msg in lp.encoding_problems(raw, 'cfg_ini'):
                    rep.error(where + '/Cfg.ini', msg)
                text = raw.decode('utf-16')
                langs = re.findall(r'^Lang(\d+)=(.*?)\s*$', text, re.M)
                mn = [n for n, v in langs if v.strip().endswith(',mn')]
                if not mn:
                    rep.error(where, 'Cfg.ini has no "LangN=Монгол,mn" entry')
                else:
                    nums = [int(n) for n, _ in langs]
                    if sorted(nums) != list(range(1, len(nums) + 1)):
                        rep.error(where, 'Cfg.ini Lang list is not 1..N: %s' % nums)
                    # lang.ini LangIndex is 0-based over this list
                    if verbose:
                        print('    %-40s Lang%s=%s  (LangIndex %d)'
                              % ('dist/%s/Cfg.ini' % model, mn[0],
                                 dict(langs)[mn[0]], int(mn[0]) - 1))
                # the loose text.xml and the reference copy must agree
                a = os.path.join(dist, model, 'text.xml')
                b = os.path.join(dist, model, 'reference', 'app', 'Text', 'mn', 'text.xml')
                if os.path.isfile(a) and os.path.isfile(b):
                    if open(a, 'rb').read() != open(b, 'rb').read():
                        rep.error(where, 'text.xml and reference/app/Text/mn/text.xml differ')

        distlan = j('dist-lan')
        if os.path.isdir(distlan):
            for model in sorted(os.listdir(distlan)):
                where = '%s :: dist-lan/%s' % (kind, model)
                cfgx = os.path.join(distlan, model, 'app', 'config.xml')
                if not os.path.isfile(cfgx):
                    # F87 Wired has no <language.info>; build_lan.py says so and
                    # ships the .lan anyway.  Selectable by system locale only.
                    rep.warning(where, 'no app/config.xml - Mongolian cannot be made the '
                                       'default for this model (known for F87 Wired)')
                    continue
                raw = open(cfgx, 'rb').read()
                for msg in lp.encoding_problems(raw, 'config_xml'):
                    rep.error(where + '/config.xml', msg)
                t = raw.decode('utf-8-sig')
                if 'value="1104"' not in t:
                    rep.error(where, 'config.xml does not list <lan value="1104"/> - the '
                                     'Mongolian file will never be loaded')
                if 'default_lan="1104"' not in t and verbose:
                    print('    %-40s listed but not default' % ('dist-lan/%s/config.xml' % model))


def check_zips(rep, repo_root, kind, verbose):
    """Every dist/*.zip must contain exactly the loose files next to it."""
    for sub in ('dist', 'dist-lan'):
        d = os.path.join(repo_root, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith('.zip'):
                continue
            zpath = os.path.join(d, name)
            where = '%s :: %s/%s' % (kind, sub, name)
            stem = name[:-len('.zip')]
            folder = os.path.join(d, stem[:-3] if stem.endswith('_mn') else stem)
            if not os.path.isdir(folder):
                rep.warning(where, 'no matching folder to compare against')
                continue
            try:
                zf = zipfile.ZipFile(zpath)
            except Exception as exc:                          # noqa: BLE001
                rep.error(where, 'not a readable zip: %s' % exc)
                continue
            bad = zf.testzip()
            if bad:
                rep.error(where, 'corrupt member: %s' % bad)

            on_disk = {}
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    p = os.path.join(root, f)
                    rel = os.path.relpath(p, folder).replace('\\', '/')
                    on_disk[rel] = open(p, 'rb').read()
            in_zip = {i.filename: zf.read(i) for i in zf.infolist() if not i.is_dir()}

            only_disk = sorted(set(on_disk) - set(in_zip))
            only_zip = sorted(set(in_zip) - set(on_disk))
            differ = sorted(k for k in set(on_disk) & set(in_zip) if on_disk[k] != in_zip[k])
            if only_disk:
                rep.error(where, 'zip is missing %d file(s) present in the folder: %s'
                          % (len(only_disk), ', '.join(only_disk[:5])))
            if only_zip:
                rep.error(where, 'zip has %d file(s) not in the folder: %s'
                          % (len(only_zip), ', '.join(only_zip[:5])))
            if differ:
                rep.error(where, 'zip content differs from the folder for: %s'
                          % ', '.join(differ[:5]))
            if verbose and not (only_disk or only_zip or differ):
                print('    %-46s %d files match the folder' % (sub + '/' + name, len(in_zip)))


def check_translation_sources(rep, repo_root, kind, verbose):
    """The mn*.json we hand-edit: metadata must be marked, values must be text."""
    for repo_name, rel, _key_is_en, _desc in lp.TRANSLATION_SOURCES:
        if repo_name != kind:
            continue
        path = os.path.join(repo_root, rel)
        if not os.path.isfile(path):
            rep.error('%s :: %s' % (kind, rel), 'translation source missing')
            continue
        where = '%s :: %s' % (kind, rel)
        strings, meta = lp.load_translation_source(path)
        bad = [k for k, v in strings.items() if not isinstance(v, str)]
        if bad:
            rep.error(where, 'non-string value(s) outside the "_" namespace: %s'
                      % ', '.join(bad[:6]))
        # A non-"_" key holding a list/dict is exactly the shape that leaked into
        # config/language.json before.  Catch it at the source too.
        if verbose:
            print('    %-46s %4d strings, %d metadata key(s)'
                  % (rel, len(strings), len(meta)))


def check_metadata_not_shipped(rep, repo_root, kind):
    """Cross-check: no metadata key from mn.json exists in the shipped file."""
    if kind != 'aula-driver-mn':
        return
    src = os.path.join(repo_root, 'tools', 'mn.json')
    lang = os.path.join(repo_root, 'config', 'language.json')
    if not (os.path.isfile(src) and os.path.isfile(lang)):
        return
    _strings, meta = lp.load_translation_source(src)
    data, _raw = lp.read_web_json_all(lang)
    shipped = data.get('mn', {})
    leaked = [k for k in meta if k in shipped]
    if leaked:
        rep.error('%s :: config/language.json [mn]' % kind,
                  'mn.json metadata reached the shipped locale: %s' % ', '.join(leaked))


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def verify_repo(repo_root, verbose):
    rep = Report()
    kind = lp.repo_kind(repo_root)
    if kind is None or kind == 'driver':
        return None, kind

    baseline = load_baseline(repo_root)
    print('\n== %s   (%s)' % (kind, repo_root))
    if baseline:
        print('   baseline: tools/vendor-baseline.json generated %s, %d model(s)'
              % (baseline.get('generated', '?'), len(baseline.get('models', {}))))
    else:
        print('   baseline: MISSING - run tools/qa/snapshot_vendor.py')
        rep.warning(kind, 'tools/vendor-baseline.json is missing')

    artifacts = lp.shipped_artifacts(repo_root, kind)
    if not artifacts:
        rep.error(kind, 'no shipped locale artifacts found')

    for label, path, family in artifacts:
        check_artifact(rep, repo_root, kind, label, path, family, baseline, verbose)

    check_family_extras(rep, repo_root, kind, verbose)
    check_zips(rep, repo_root, kind, verbose)
    check_translation_sources(rep, repo_root, kind, verbose)
    check_metadata_not_shipped(rep, repo_root, kind)
    return rep, kind


def self_test():
    """Deliberately break a copy of each family and confirm we complain."""
    import shutil
    import tempfile

    print('SELF-TEST - a verifier that has never failed is not known to work.\n')
    base = lp.find_sibling('aula-driver-mn')
    fs = lp.find_sibling('aula-fseries-mn')
    ky = lp.find_sibling('kysona-m600-mn')
    tmp = tempfile.mkdtemp(prefix='qa-selftest-')
    failures = 0

    counter = [0]

    def scan(root):
        rep = Report()
        kind = lp.repo_kind(root)
        baseline = load_baseline(root)
        for label, path, family in lp.shipped_artifacts(root, kind):
            check_artifact(rep, root, kind, label, path, family, baseline, False)
        check_family_extras(rep, root, kind, False)
        check_translation_sources(rep, root, kind, False)
        check_metadata_not_shipped(rep, root, kind)
        return ['%s | %s' % (w, m) for w, m in rep.fail]

    def run(title, repo_src, mutate, expect):
        """Break one thing, and require the check we aimed at to be the one
        that fires.  The repos already have known failures; counting "any
        error" would let a broken check pass on somebody else's complaint."""
        nonlocal failures
        counter[0] += 1
        dst = os.path.join(tmp, 'case%02d' % counter[0])
        # Copy only what the checks read.  The vendor originals under .work*/ are
        # left out on purpose: the self-test must exercise the CI path, where the
        # committed baseline is the only reference available.
        shutil.copytree(repo_src, dst, ignore=shutil.ignore_patterns(
            '.git', 'installers', '.work', '.work2', 'dist-auto', 'image',
            'css', 'js', 'plug', 'firmware', '*.zip'))
        before = set(scan(dst))
        mutate(dst)
        new = [m for m in scan(dst) if m not in before]
        hit = [m for m in new if expect.lower() in m.lower()]
        if hit:
            print('  CAUGHT  %-44s %s' % (title, hit[0].split(' | ', 1)[-1][:92]))
        else:
            failures += 1
            print('  MISSED  %-44s expected /%s/, got: %s'
                  % (title, expect, (new[0][:70] if new else 'no new error at all')))

    # 1. the real bug: "_" metadata (one of them an ARRAY) in the shipped locale
    def inject_metadata(root):
        p = os.path.join(root, 'config', 'language.json')
        d = json.load(io.open(p, encoding='utf-8'))
        d['mn']['_intentionally_english'] = ['Polling Rate', 'DPI']
        d['mn']['_note'] = 'documentation, not UI text'
        json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    run('web: "_" metadata + array in mn locale', base, inject_metadata,
        'metadata key(s) reached the shipped file')

    # 2. a key the vendor defines, dropped from mn
    def drop_key(root):
        p = os.path.join(root, 'config', 'language.json')
        d = json.load(io.open(p, encoding='utf-8'))
        for k in list(d['mn'])[:3]:
            del d['mn'][k]
        json.dump(d, io.open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    run('web: 3 keys missing from mn', base, drop_key, 'are missing or under-counted')

    # 3. duplicate JSON key, which json.load would silently swallow
    def dupe_key(root):
        p = os.path.join(root, 'config', 'language.json')
        text = io.open(p, encoding='utf-8').read()
        text = text.replace('"mn": {', '"mn": {\n    "welcome": "FIRST",', 1)
        io.open(p, 'w', encoding='utf-8').write(text)
    run('web: duplicate JSON key', base, dupe_key, 'duplicate JSON key')

    # 4. wrong encoding: UTF-16 pack rewritten as UTF-8
    def wrong_encoding(root):
        p = os.path.join(root, 'dist', 'AULA_F65_driver', 'text.xml')
        text = open(p, 'rb').read().decode('utf-16')
        open(p, 'wb').write(text.encode('utf-8'))
    run('bycombo4: UTF-16 file written as UTF-8', fs, wrong_encoding, 'wrong BOM')

    # 5. LF instead of CRLF in a .lan
    def lf_endings(root):
        p = os.path.join(root, 'dist-lan', 'AULA_F98PRO_driver', 'app', 'language', '1104.lan')
        text = open(p, 'rb').read().decode('utf-16').replace('\r\n', '\n')
        open(p, 'wb').write(text.encode('utf-16'))
    run('lan: CRLF flattened to LF', fs, lf_endings, 'no CRLF at all')

    # 6. Cfg.ini loses the Mongolian entry
    def strip_cfg(root):
        p = os.path.join(root, 'dist', 'AULA_F65_driver', 'reference', 'app', 'Cfg.ini')
        text = open(p, 'rb').read().decode('utf-16')
        text = re.sub(r'(?m)^Lang\d+=.*,mn\s*$', '', text)
        open(p, 'wb').write(text.encode('utf-16'))
    run('bycombo4: Cfg.ini lost Монгол,mn', fs, strip_cfg, 'Cfg.ini has no')

    # 7. config.xml no longer lists 1104
    def strip_1104(root):
        p = os.path.join(root, 'dist-lan', 'AULA_F75MAX_driver', 'app', 'config.xml')
        t = open(p, 'rb').read().decode('utf-8-sig').replace('1104', '1033')
        open(p, 'wb').write(b'\xef\xbb\xbf' + t.encode('utf-8'))
    run('lan: config.xml stopped listing 1104', fs, strip_1104, 'does not list')

    # 8. a value blanked out
    def blank_value(root):
        p = os.path.join(root, 'dist', 'KYSONA_M600_driver', '2-Монгол.xml')
        t = open(p, 'rb').read().decode('utf-8-sig')
        t = re.sub(r'<label_DPIGrade>[^<]*</label_DPIGrade>',
                   '<label_DPIGrade></label_DPIGrade>', t, count=1)
        open(p, 'wb').write(b'\xef\xbb\xbf' + t.encode('utf-8'))
    run('kysona: a translated value blanked out', ky, blank_value, 'blank where the vendor has text')

    # 9. a ComboBoxName control id translated
    def translate_id(root):
        p = os.path.join(root, 'dist', 'KYSONA_M600_driver', '2-Монгол.xml')
        t = open(p, 'rb').read().decode('utf-8-sig')
        t = re.sub(r'<ComboBoxName>([^<]*)</ComboBoxName>',
                   '<ComboBoxName>Монгол нэр</ComboBoxName>', t, count=1)
        open(p, 'wb').write(b'\xef\xbb\xbf' + t.encode('utf-8'))
    run('kysona: ComboBoxName control id translated', ky, translate_id, 'control id(s) were translated')

    # 10. a numeric value "translated"
    def break_number(root):
        p = os.path.join(root, 'dist', 'KYSONA_M600_driver', '2-Монгол.xml')
        t = open(p, 'rb').read().decode('utf-8-sig')
        t = re.sub(r'>(\d+)</', r'>\g<1> мс</', t, count=1)
        open(p, 'wb').write(b'\xef\xbb\xbf' + t.encode('utf-8'))
    run('kysona: numeric value altered', ky, break_number, 'numeric/unit value(s) changed')

    # 11. the F75 already has a real key collision (two English strings on one
    #     key).  Resolving it must make the check go QUIET - a check that can
    #     only shout is not a check.
    def resolve_collision(root):
        p = os.path.join(root, 'dist', 'AULA_F75_driver', 'text.xml')
        t = open(p, 'rb').read().decode('utf-16')
        # give the second occurrence of each colliding key its own Mongolian
        for key in ('tc_yun9', 'tc_yun10'):
            marks = [m for m in re.finditer(r'<%s>([^<]*)</%s>' % (key, key), t)]
            if len(marks) > 1:
                m = marks[1]
                t = t[:m.start()] + '<%s>ӨӨР ОРЧУУЛГА</%s>' % (key, key) + t[m.end():]
        open(p, 'wb').write(t.encode('utf-16'))

    dst = os.path.join(tmp, 'case11')
    shutil.copytree(fs, dst, ignore=shutil.ignore_patterns(
        '.git', 'installers', '.work', '.work2', 'dist-auto', 'image',
        'css', 'js', 'plug', 'firmware', '*.zip'))
    before = [m for m in scan(dst) if 'two DIFFERENT English' in m]
    resolve_collision(dst)
    after = [m for m in scan(dst) if 'two DIFFERENT English' in m]
    if before and not after:
        print('  CAUGHT  %-44s %d collision error(s) -> 0 once disambiguated'
              % ('F75 collision resolved silences the check', len(before)))
    else:
        failures += 1
        print('  MISSED  %-44s before=%d after=%d (expected some -> none)'
              % ('F75 collision resolved silences the check', len(before), len(after)))


    shutil.rmtree(tmp, ignore_errors=True)
    print('\n%d of 11 self-test cases behaved wrongly '
          '(10 deliberate breakages + 1 "does it go quiet when fixed").' % failures)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', action='append', default=[])
    ap.add_argument('--verbose', '-v', action='store_true')
    ap.add_argument('--self-test', action='store_true',
                    help='break known-good files on purpose and confirm we notice')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    repos = list(args.repo)
    if not repos:
        for name in ('aula-driver-mn', 'aula-fseries-mn', 'kysona-m600-mn'):
            found = lp.find_sibling(name)
            if found:
                repos.append(found)
    if not repos:
        print('No localisation repos found. Pass --repo <path>.')
        return 2

    total_fail = total_warn = total_checked = 0
    for repo in repos:
        rep, kind = verify_repo(os.path.abspath(repo), args.verbose)
        if rep is None:
            print('\n== %s   SKIPPED (not a localisation repo)' % repo)
            continue
        for w, m in rep.fail:
            print('   FAIL  %s' % w)
            print('         %s' % m)
        for w, m in rep.warn:
            print('   warn  %s' % w)
            print('         %s' % m)
        print('   %d artifact(s) checked, %d failure(s), %d warning(s)'
              % (rep.checked, len(rep.fail), len(rep.warn)))
        total_fail += len(rep.fail)
        total_warn += len(rep.warn)
        total_checked += rep.checked

    print('\n%s  -  %d artifacts, %d failures, %d warnings'
          % ('ALL ARTIFACTS PASS' if not total_fail else 'PROBLEMS FOUND',
             total_checked, total_fail, total_warn))
    return 1 if total_fail else 0


if __name__ == '__main__':
    sys.exit(main())
