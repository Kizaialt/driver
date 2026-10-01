#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared reader for every locale artifact family in the Peaklab driver
localisation projects.  Nothing in here writes; it only parses and describes.

Four families ship, each with its own encoding contract:

  web_json    aula-driver-mn/config/language.json
              UTF-8, no BOM, JSON object of locales.  The "mn" locale is ours.

  bycombo4    aula-fseries-mn/dist/<MODEL>/text.xml        (OemDrv.exe)
              UTF-16 LE + BOM, CRLF, tab indent, <root><section><tc_key>.

  lan         aula-fseries-mn/dist-lan/<MODEL>/app/language/1104.lan
              UTF-16 LE + BOM, CRLF, INI-style "[Section]" + "123=Text".
              Key NUMBERS are not stable across models - identity for
              cross-model work is the English text, not the number.

  kysona_xml  kysona-m600-mn/dist/<MODEL>/<n>-Монгол.xml
              UTF-8 + BOM, CRLF, 2-space indent, root named after the language.

Every reader returns a Doc:

  Doc.entries  [Entry(key, value, section)]  in document order
  Doc.raw      the exact bytes on disk
  Doc.path     absolute path

`key` is the artifact-stable identity inside one file (element path, section +
key name, section + number, or JSON key).  It is NOT comparable across models
in the .lan family - see verify_artifacts.py for how that is handled.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import namedtuple

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

Entry = namedtuple('Entry', 'key value section')

CYRILLIC = re.compile(r'[Ѐ-ӿ]')

# Values that are pure numbers - optionally with a unit - are never translated
# and must survive byte-identical: "100", "0.5 ms", "1000Hz", "2.4G".
#
# A DIGIT IS REQUIRED.  A bare unit word like "ms" or "Min" standing alone is a
# UI label, not a value: "ms" -> "мс" and "Min" -> "минут" are correct
# translations, and an earlier version of this rule flagged all six F-series
# packs for them.
NUMERIC_ONLY = re.compile(r'^[\s+\-]*\d[\s\d.,:%+\-/()x*]*\s*(ms|mm|sec|min|Hz|s|%|G)?\s*$', re.I)

# Values that carry no letters at all (punctuation, separators, "---").
NO_LETTERS = re.compile(r'^[^0-9A-Za-zЀ-ӿ]*$')


class Doc(object):
    def __init__(self, path, family, entries, raw, root_tag=None):
        self.path = path
        self.family = family
        self.entries = entries
        self.raw = raw
        self.root_tag = root_tag

    @property
    def keys(self):
        return [e.key for e in self.entries]

    def as_map(self):
        return {e.key: e.value for e in self.entries}

    def __repr__(self):
        return '<Doc %s %s %d entries>' % (self.family, os.path.basename(self.path), len(self.entries))


# --------------------------------------------------------------------------
# encoding contracts
# --------------------------------------------------------------------------

BOM_UTF16LE = b'\xff\xfe'
BOM_UTF8 = b'\xef\xbb\xbf'

FAMILY_ENCODING = {
    # family     -> (required BOM or None, label, crlf required)
    'web_json':   (None,        'UTF-8 (no BOM)',    False),
    'bycombo4':   (BOM_UTF16LE, 'UTF-16 LE + BOM',   True),
    'lan':        (BOM_UTF16LE, 'UTF-16 LE + BOM',   True),
    'kysona_xml': (BOM_UTF8,    'UTF-8 + BOM',       True),
    'cfg_ini':    (BOM_UTF16LE, 'UTF-16 LE + BOM',   True),
    'config_xml': (BOM_UTF8,    'UTF-8 + BOM',       True),
}


def display_width(s):
    """Approximate rendered width in 'half-width cells'.

    A plain character count is useless for judging whether a translation still
    fits its control, because the vendor's own comparison locales are Chinese
    and Korean: 设置 is 2 characters but as wide as 4 Latin ones.  East Asian
    Wide and Fullwidth characters therefore count 2, combining marks 0, and
    everything else 1.  Cyrillic is narrow, so Mongolian counts 1 per letter -
    which is exactly why a Mongolian word can be short on screen and still
    blow past a control sized for Chinese.
    """
    import unicodedata
    w = 0
    for ch in s or '':
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return w


def sibling_locales(repo_root, family, model, kind=None):
    """Every OTHER locale file the vendor ships for this model, as
    {locale_name: path}.  These are the width evidence: text the vendor itself
    shipped means the control tolerated that width in production software."""
    kind = kind or repo_kind(repo_root)
    out = {}
    if kind == 'aula-fseries-mn' and family == 'bycombo4':
        base = os.path.join(repo_root, '.work', model, 'app', 'Text')
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                p = os.path.join(base, d, 'text.xml')
                if os.path.isfile(p):
                    out[d] = p
    elif kind == 'aula-fseries-mn' and family == 'lan':
        base = os.path.join(repo_root, '.work2', model, 'app', 'language')
        if os.path.isdir(base):
            for n in sorted(os.listdir(base)):
                if n.endswith('.lan'):
                    out[n[:-4]] = os.path.join(base, n)
    elif kind == 'kysona-m600-mn':
        base = os.path.join(repo_root, '.work', model, 'app', 'Language')
        if os.path.isdir(base):
            for n in sorted(os.listdir(base)):
                if re.match(r'^\d+-.*\.xml$', n):
                    out[n[:-4]] = os.path.join(base, n)
    return out


# Families whose files never contain a multi-line value, so any bare LF is
# drift rather than content.  The locale files themselves are NOT in this set:
# the vendor embeds a real line break inside a few long messages.
ABSOLUTE_CRLF = {'cfg_ini', 'config_xml'}

# Families where document order is part of the contract.  JSON is a lookup map;
# its key order is meaningless and must not be compared.
ORDERED_FAMILIES = {'bycombo4', 'lan', 'kysona_xml'}


def line_ending_counts(raw, family):
    """(crlf, lf) counts, decoded per the family's encoding."""
    bom, _label, _need = FAMILY_ENCODING[family]
    if bom == BOM_UTF16LE:
        return raw.count(b'\r\x00\n\x00'), raw.count(b'\n\x00')
    return raw.count(b'\r\n'), raw.count(b'\n')


def bare_lf_count(raw, family):
    """Newlines that are NOT part of a CRLF pair.

    Not all of these are defects: the vendor embeds a line break inside a few
    long message values.  Compare against the vendor's own count rather than
    demanding zero.
    """
    crlf, lf = line_ending_counts(raw, family)
    return lf - crlf


def encoding_problems(raw, family):
    """BOM and 'has line endings at all' - the parts that are absolute.

    Bare-LF drift is relative to the vendor and is checked separately, against
    the recorded vendor count.
    """
    bom, label, need_crlf = FAMILY_ENCODING[family]
    out = []

    if bom is None:
        if raw[:3] == BOM_UTF8 or raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            out.append('has a BOM but this family ships %s' % label)
    elif not raw.startswith(bom):
        out.append('wrong BOM: expected %s (%s), found %r'
                   % (bom.hex(), label, raw[:4]))

    if need_crlf:
        crlf, lf = line_ending_counts(raw, family)
        if lf == 0:
            out.append('no line endings at all')
        elif crlf == 0:
            out.append('no CRLF at all (%d bare LF) - this family ships CRLF' % lf)
        elif family in ABSOLUTE_CRLF and lf > crlf:
            out.append('%d bare LF line ending(s) - Cfg.ini and config.xml are pure CRLF '
                       'in the vendor build, they hold no multi-line values' % (lf - crlf))
    return out


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------

def read_web_json(path, locale='mn'):
    """aula-driver-mn/config/language.json -> the requested locale."""
    raw = open(path, 'rb').read()
    data = json.loads(raw.decode('utf-8-sig'))
    if locale not in data:
        raise KeyError('%s has no "%s" locale' % (path, locale))
    entries = [Entry(k, v, locale) for k, v in data[locale].items()]
    return Doc(path, 'web_json', entries, raw)


def read_web_json_all(path):
    raw = open(path, 'rb').read()
    return json.loads(raw.decode('utf-8-sig')), raw


def _utf16_text(raw):
    return raw.decode('utf-16')


def read_bycombo4(path):
    """aula-fseries text.xml (UTF-16).  key = '<section>/<tag>'."""
    raw = open(path, 'rb').read()
    text = _utf16_text(raw).replace('encoding="utf-16"', 'encoding="utf-8"')
    root = ET.fromstring(text)
    entries = []
    for section in root:
        for el in section:
            entries.append(Entry('%s/%s' % (section.tag, el.tag), el.text or '', section.tag))
    return Doc(path, 'bycombo4', entries, raw, root.tag)


def read_lan(path):
    """.lan file (UTF-16, INI-style).  key = '<section>/<number>'."""
    raw = open(path, 'rb').read()
    text = _utf16_text(raw)
    entries = []
    section = ''
    for line in text.replace('\r\n', '\n').split('\n'):
        s = line.strip()
        if not s:
            continue
        if s.startswith('[') and s.endswith(']'):
            section = s[1:-1]
        elif '=' in s:
            k, _sep, v = s.partition('=')
            entries.append(Entry('%s/%s' % (section, k.strip()), v, section))
    return Doc(path, 'lan', entries, raw)


def read_kysona_xml(path):
    """KYSONA language XML (UTF-8 + BOM).  key = 'Parent/Child/Leaf'."""
    raw = open(path, 'rb').read()
    root = ET.fromstring(raw.decode('utf-8-sig'))
    entries = []

    def walk(node, parts):
        kids = list(node)
        if kids:
            for c in kids:
                walk(c, parts + [node.tag])
        else:
            entries.append(Entry('/'.join(parts + [node.tag]), node.text or '',
                                 parts[0] if parts else ''))

    for child in root:
        walk(child, [])
    return Doc(path, 'kysona_xml', entries, raw, root.tag)


READERS = {
    'web_json': read_web_json,
    'bycombo4': read_bycombo4,
    'lan': read_lan,
    'kysona_xml': read_kysona_xml,
}


def read(path, family, **kw):
    return READERS[family](path, **kw)


# --------------------------------------------------------------------------
# translation-source readers (the mn.json files we hand-edit)
# --------------------------------------------------------------------------

TRANSLATION_SOURCES = [
    # (repo dir name, relative path, key_is_english, description)
    ('aula-driver-mn',  'tools/mn.json',     False, 'WIN60/68 HE web driver'),
    ('aula-fseries-mn', 'tools/mn.json',     False, 'AULA F-series BYCOMBO4 pack'),
    ('aula-fseries-mn', 'tools/mn_lan.json', True,  'AULA .lan family pack'),
    ('kysona-m600-mn',  'tools/mn.json',     True,  'KYSONA M600 mouse pack'),
]


def load_translation_source(path):
    """Return (strings, metadata) for any of the four mn*.json shapes.

    Two shapes exist:
      flat      {"_comment": ..., "key": "text", ..., "_overrides": {...}}
      wrapped   {"_comment": ..., "strings": {...}, "_keep_as_is": [...]}
    Keys starting with "_" are metadata and must never reach a shipped file.
    """
    with io.open(path, encoding='utf-8') as fh:
        data = json.load(fh)

    meta = {k: v for k, v in data.items() if k.startswith('_')}
    if 'strings' in data and isinstance(data['strings'], dict):
        strings = dict(data['strings'])
        meta.update({k: v for k, v in data.items()
                     if k != 'strings' and k.startswith('_')})
    else:
        strings = {k: v for k, v in data.items() if not k.startswith('_')}

    overrides = meta.get('_overrides') or {}
    if isinstance(overrides, dict):
        overrides = {k: v for k, v in overrides.items() if not k.startswith('_')}
        meta['_overrides'] = overrides
    return strings, meta


# --------------------------------------------------------------------------
# repo layout
# --------------------------------------------------------------------------

def repo_kind(repo_root):
    """Identify which of the four repos a directory is, by its contents."""
    j = lambda *p: os.path.join(repo_root, *p)
    if os.path.isfile(j('config', 'language.json')) and os.path.isfile(j('tools', 'apply-mn.js')):
        return 'aula-driver-mn'
    if os.path.isfile(j('tools', 'mn_lan.json')):
        return 'aula-fseries-mn'
    if os.path.isfile(j('tools', 'mn.json')) and os.path.isdir(j('dist')) and \
            any(n.startswith('KYSONA') for n in os.listdir(j('dist'))):
        return 'kysona-m600-mn'
    if os.path.isfile(j('tools', 'checklinks.py')):
        return 'driver'
    return None


def find_sibling(name, start=None):
    """Locate a sibling repo checkout next to this one, or under ./ in CI."""
    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here)),
                 os.path.dirname(os.path.dirname(os.path.dirname(here))),
                 os.getcwd(), os.path.join(os.getcwd(), '..')):
        cand = os.path.join(base, name)
        if os.path.isdir(cand):
            return os.path.abspath(cand)
    return None


def shipped_artifacts(repo_root, kind=None):
    """Enumerate every locale file this repo ships, as (label, path, family).

    Only files that are committed and customer-visible: the loose pack files
    and, for aula-driver-mn, the merged config/language.json.  Vendor originals
    under .work*/ and installers/ are gitignored and are NOT listed here.
    """
    kind = kind or repo_kind(repo_root)
    j = lambda *p: os.path.join(repo_root, *p)
    out = []

    if kind == 'aula-driver-mn':
        out.append(('config/language.json [mn]', j('config', 'language.json'), 'web_json'))

    elif kind == 'aula-fseries-mn':
        dist = j('dist')
        if os.path.isdir(dist):
            for model in sorted(os.listdir(dist)):
                p = os.path.join(dist, model, 'text.xml')
                if os.path.isfile(p):
                    out.append(('dist/%s/text.xml' % model, p, 'bycombo4'))
        distlan = j('dist-lan')
        if os.path.isdir(distlan):
            for model in sorted(os.listdir(distlan)):
                p = os.path.join(distlan, model, 'app', 'language', '1104.lan')
                if os.path.isfile(p):
                    out.append(('dist-lan/%s/1104.lan' % model, p, 'lan'))

    elif kind == 'kysona-m600-mn':
        dist = j('dist')
        if os.path.isdir(dist):
            for model in sorted(os.listdir(dist)):
                d = os.path.join(dist, model)
                if not os.path.isdir(d):
                    continue
                for name in sorted(os.listdir(d)):
                    if re.match(r'^\d+-.*\.xml$', name):
                        out.append(('dist/%s/%s' % (model, name),
                                    os.path.join(d, name), 'kysona_xml'))
    return out


def vendor_original(repo_root, family, model, kind=None):
    """Path to the vendor's own English file for a model, if the gitignored
    working copy is present locally.  Returns None in CI, where it never is."""
    kind = kind or repo_kind(repo_root)
    j = lambda *p: os.path.join(repo_root, *p)
    if kind == 'aula-fseries-mn' and family == 'bycombo4':
        p = j('.work', model, 'app', 'Text', 'en', 'text.xml')
    elif kind == 'aula-fseries-mn' and family == 'lan':
        p = j('.work2', model, 'app', 'language', '1033.lan')
    elif kind == 'kysona-m600-mn':
        p = j('.work', model, 'app', 'Language', '0-English.xml')
    else:
        return None
    return p if os.path.isfile(p) else None


def model_of(label):
    """'dist/AULA_F65_driver/text.xml' -> 'AULA_F65_driver'."""
    parts = label.replace('\\', '/').split('/')
    return parts[1] if len(parts) > 1 else ''
