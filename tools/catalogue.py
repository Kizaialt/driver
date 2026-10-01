#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build data/models.json - the catalogue the driver page renders.

    python tools/catalogue.py

The Mongolian-ready models are curated by hand below. Everything else is
lifted from the vendor listings we scraped, so the fallback links stay honest
rather than being retyped.
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AULA_LINKS = os.path.join(ROOT, 'tools', 'aula_links.json')
OUT = os.path.join(ROOT, 'data', 'models.json')

AULA_BASE = 'https://www.aulastar.com'
AULA_LIST = 'https://www.aulastar.com/keyboard/'
KYSONA_LIST = 'https://shop.kysona.com/pages/downloads'

WEB_DRIVER = 'https://kizaialt.github.io/winhe-driver/'
FSERIES_REL = 'https://github.com/Kizaialt/aula-fseries-mn/releases/download/v1.6/'
KYSONA_REL = 'https://github.com/Kizaialt/kysona-m600-mn/releases/download/v1.6/'


def aula(url):
    """Vendor links are page-relative; make them absolute and URL-safe.

    A few AULA installers sit at paths with literal spaces
    ("AULA  F68 driver.exe"), which browsers tolerate in an href but curl and
    some proxies do not. Encode the path, leave the query string alone - its
    token is already encoded and re-encoding would corrupt it.
    """
    if not url.startswith('http'):
        url = AULA_BASE + url
    head, sep, query = url.partition('?')
    return head.replace(' ', '%20') + sep + query


# ---------------------------------------------------------------- Mongolian
# kind: 'web'  -> open our translated web driver, nothing to install
#       'pack' -> vendor driver first, then our language pack
MONGOLIAN = [
    {
        'brand': 'AULA', 'name': 'WIN 60 HE', 'type': 'kb', 'kind': 'web',
        'alias': ['win60', 'win 60', 'вин 60', 'si2825',
                  'win 60 standard', 'win 60 standard edition', 'standard'],
        'note': 'Соронзон (Hall effect) гар',
        'web': WEB_DRIVER,
    },
    {
        'brand': 'AULA', 'name': 'WIN 68 HE', 'type': 'kb', 'kind': 'web',
        'alias': ['win68', 'win 68', 'вин 68', 'si2828',
                  'win 68 standard', 'standard'],
        'note': 'Соронзон (Hall effect) гар',
        'web': WEB_DRIVER,
    },
    {
        'brand': 'AULA', 'name': 'F65', 'type': 'kb', 'kind': 'pack',
        'alias': ['ф65', 'f 65'],
        'vendor': None,          # filled from the scrape
        'pack': FSERIES_REL + 'AULA_F65_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F65_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F75', 'type': 'kb', 'kind': 'pack',
        'alias': ['ф75', 'f 75'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F75_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F75_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F99', 'type': 'kb', 'kind': 'pack',
        'alias': ['ф99', 'f 99'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F99_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F99_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F108', 'type': 'kb', 'kind': 'pack',
        'alias': ['ф108', 'f 108'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F108_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F108_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F65 Pro', 'type': 'kb', 'kind': 'pack',
        'alias': ['f65pro', 'ф65 про', 'f65 pro'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F65Pro_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F65Pro_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F99 Pro', 'type': 'kb', 'kind': 'pack',
        'alias': ['f99pro', 'ф99 про', 'f99 pro'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F99Pro_driver_mn.zip',
        'auto': FSERIES_REL + 'AULA_F99Pro_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F75 MAX', 'type': 'kb', 'kind': 'pack',
        'alias': ['f75max', 'ф75 макс'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F75MAX_driver_mn_auto.zip',
        'auto': FSERIES_REL + 'AULA_F75MAX_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F98 Pro', 'type': 'kb', 'kind': 'pack',
        'alias': ['f98pro', 'f98 pro', 'f98pro v3', 'ф98'],
        'note': 'F98 Pro V3 загварт мөн тохирно',
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F98PRO_driver_mn_auto.zip',
        'auto': FSERIES_REL + 'AULA_F98PRO_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F106 Pro', 'type': 'kb', 'kind': 'pack',
        'alias': ['f106pro', 'f106 pro', 'ф106'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F106Pro_driver_mn_auto.zip',
        'auto': FSERIES_REL + 'AULA_F106Pro_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F108 Pro', 'type': 'kb', 'kind': 'pack',
        'alias': ['f108pro', 'f108 pro', 'ф108 про'],
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F108Pro_driver_mn_auto.zip',
        'auto': FSERIES_REL + 'AULA_F108Pro_driver_mn_auto.zip',
    },
    {
        'brand': 'AULA', 'name': 'F87 Wired', 'type': 'kb', 'kind': 'pack',
        'alias': ['f87 wired', 'f87wired', 'ф87 утастай', 'f87'],
        'note': 'Хэлээ Settings → Language-с сонгоно',
        'vendor': None,
        'pack': FSERIES_REL + 'AULA_F87_Wired_driver_mn_auto.zip',
        'auto': FSERIES_REL + 'AULA_F87_Wired_driver_mn_auto.zip',
    },
    {
        'brand': 'KYSONA', 'name': 'M600', 'type': 'mouse', 'kind': 'pack',
        # filter.js transliterates Cyrillic to Latin before matching, so a
        # Cyrillic spelling is only needed where it does not transliterate
        # onto the Latin one ("кисона" -> kisona, not kysona).
        'alias': ['м600', 'm 600', 'm617', 'aztec', 'aztek', 'кисона'],
        'note': 'M617, Aztec загварт мөн тохирно',
        'vendor': 'https://cdn.shopify.com/s/files/1/0809/0697/7595/files/M600.exe?v=1731988923',
        'vendor_page': KYSONA_LIST,
        'pack': KYSONA_REL + 'KYSONA_M600_driver_mn.zip',
        'auto': KYSONA_REL + 'KYSONA_M600_driver_mn_auto.zip',
    },
    {
        'brand': 'KYSONA', 'name': 'M600 V2', 'type': 'mouse', 'kind': 'pack',
        'alias': ['м600 v2', 'm600v2'],
        'vendor': 'https://cdn.shopify.com/s/files/1/0809/0697/7595/files/KYSONA_M600_V2_mouse_software.rar?v=1742263715',
        'vendor_page': KYSONA_LIST,
        'pack': KYSONA_REL + 'KYSONA_M600_V2_driver_mn.zip',
        'auto': KYSONA_REL + 'KYSONA_M600_V2_driver_mn_auto.zip',
        'note': '.rar дотор ирнэ — эхлээд задална',
    },
]

# vendor download for the four F-series models, taken from the scrape
FSERIES_SCRAPE_KEY = {'F65': 'F65', 'F65 Pro': 'F65Pro', 'F75': 'F75',
                      'F99': 'F99', 'F99 Pro': 'F99Pro', 'F108': 'F108',
                      'F75 MAX': 'F75MAX', 'F98 Pro': 'F98PRO',
                      'F106 Pro': 'F106Pro', 'F108 Pro': 'F108Pro',
                      'F87 Wired': 'F87 Wired'}

# Models we deliberately do not list (other brands' resellers, ancient stock)
SKIP = set()

# Type guesses for the fallback list
MOUSE_HINT = re.compile(r'(?i)mouse|m6\d\d')


def main():
    with io.open(AULA_LINKS, encoding='utf-8') as fh:
        scraped = json.load(fh)

    models = []

    for m in MONGOLIAN:
        entry = dict(m)
        key = FSERIES_SCRAPE_KEY.get(m['name'])
        if key and key in scraped:
            entry['vendor'] = aula(scraped[key])
            entry.setdefault('vendor_page', AULA_LIST)
        entry['mn'] = True
        models.append(entry)

    known = {m['name'].upper() for m in MONGOLIAN}
    known |= {'M617', 'AZTEC', 'F65PRO', 'F99PRO', 'F75MAX', 'F98PRO',
              'F98PRO V3', 'F106PRO', 'F108PRO', 'F87 WIRED'}
    # AULA lists the same two boards under a second name on its web-drive
    # page; they point at the very driver we translated, so listing them
    # again under 'others' would send customers to the untranslated one.
    known |= {'WIN 60 STANDARD EDITION', 'WIN 68 STANDARD'}

    others = []
    for name, url in sorted(scraped.items()):
        if name.upper() in known or name in SKIP:
            continue
        target = aula(url)
        if 'aula-hub' in target:
            how = 'hub'          # AULA HUB desktop app
        elif re.match(r'^https?://(?!www\.aulastar)', target):
            how = 'web'          # vendor web driver, Chinese/English only
        else:
            how = 'exe'          # direct Windows installer
        others.append({
            'brand': 'AULA',
            'name': name,
            'type': 'mouse' if MOUSE_HINT.search(name) else 'kb',
            'kind': 'vendor',
            'how': how,
            'vendor': target,
            'vendor_page': AULA_LIST,
            'mn': False,
        })

    data = {
        'updated': '2026-08-31',
        'mongolian': models,
        'others': others,
        'links': {'aula': AULA_LIST, 'kysona': KYSONA_LIST},
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    print('wrote %s' % os.path.relpath(OUT, ROOT))
    print('  Mongolian models : %d' % len(models))
    print('  other models     : %d' % len(others))
    by_how = {}
    for o in others:
        by_how[o['how']] = by_how.get(o['how'], 0) + 1
    print('  fallback kinds   : %s' % by_how)
    missing = [m['name'] for m in models if m['kind'] == 'pack' and not m.get('vendor')]
    if missing:
        print('  WARNING: no vendor link for %s' % ', '.join(missing))


if __name__ == '__main__':
    main()
