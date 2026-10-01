#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render data/models.json into src/index.template.html and write index.html.

    python tools/catalogue.py   # refresh the catalogue from vendor data
    python tools/build.py       # then bake the page

Rows are rendered here, at build time, rather than by JavaScript in the
browser. That keeps the whole catalogue in the served HTML: it works with
JS disabled, it is indexable, and first paint does not wait on a script.
JavaScript on the page does one thing only - filter rows that already exist.

src/filter.js is inlined into the page here, so it stays one file on disk
and still costs no extra request in the browser.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, 'src', 'index.template.html')
SCRIPT = os.path.join(ROOT, 'src', 'filter.js')
DATA = os.path.join(ROOT, 'data', 'models.json')
OUT = os.path.join(ROOT, 'index.html')

ICON = {
    'kb': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M8 14h8" stroke-linecap="round"/></svg>',
    'mouse': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 6v4" stroke-linecap="round"/></svg>',
}
CHEV = '<svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>'
DL = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/></svg>'
EXT = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v6H4V6h6"/></svg>'
PC = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>'
ALERT = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>'

HOW = {'web': 'Онлайн драйвер', 'exe': 'Windows программ', 'hub': 'AULA HUB программ'}

# Folded into every row's search key so that a customer who has forgotten the
# model name can still get somewhere by typing what the thing is. Both the
# Cyrillic and the Latin spelling are here because filter.js transliterates
# the query - "хулгана" and "mouse" both have to land.
TYPE_WORDS = {
    'kb': 'гар keyboard клавиатура',
    'mouse': 'хулгана mouse',
}

# The two requirements a customer cannot discover by looking at the page.
REQ = {
    'web': 'Компьютер дээр, Chrome эсвэл Edge хөтчөөр',
    'pack': 'Windows компьютер дээр',
}

WARN_HID = (
    '<p class="warn" data-need="hid">%s<span>Энэ хөтөч дээр ажиллахгүй. '
    'Компьютер дээрх <b>Chrome</b> эсвэл <b>Edge</b> хөтчөөр нээнэ үү.</span></p>'
) % ALERT
WARN_WIN = (
    '<p class="warn" data-need="win">%s<span>Энэ нь <b>Windows</b> программ. '
    'Windows компьютер дээрээ татаж аваарай.</span></p>'
) % ALERT


def esc(s):
    return (str(s if s is not None else '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def key(m):
    parts = ([m.get('brand', ''), m.get('name', '')] + m.get('alias', [])
             + [m.get('note', ''), TYPE_WORDS.get(m.get('type'), TYPE_WORDS['kb'])])
    return ' '.join(' '.join(parts).lower().split())


def slug(m):
    """Stable per-model anchor, so one exact model can be linked to."""
    s = ('%s-%s' % (m.get('brand', ''), m.get('name', ''))).lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def icon(m):
    return ICON.get(m.get('type'), ICON['kb'])


def req(kind):
    return '<p class="req">%s<span>%s</span></p>' % (PC, REQ[kind])


def mn_row(m):
    sub = m.get('note') or ('Хулгана' if m.get('type') == 'mouse' else 'Гар')

    if m['kind'] == 'web':
        body = (
            '<ul class="steps"><li>'
            '<div class="steptitle">Онлайн драйверыг нээх</div>'
            '<div class="stephint">Юу ч суулгах шаардлагагүй. Компьютер дээрээ '
            'Chrome эсвэл Edge хөтчөөр нээгээд гараа USB-ээр залгана.</div>'
            '%s%s'
            '<a class="btn" href="%s" target="_blank" rel="noopener">%sДрайвер нээх</a>'
            '</li></ul>'
            '<div class="after">Гар холбогдоод шууд монголоор нээгдэнэ. '
            'Утас, таблет дээр, мөн Firefox, Safari дээр ажиллахгүй.</div>'
        ) % (req('web'), WARN_HID, esc(m['web']), EXT)
    else:
        # One file, one double-click. The bundle carries the vendor's own
        # installer, so there is nothing to download separately and no
        # language menu to find afterwards.
        menu = 'Setting → Language' if m.get('type') == 'mouse' else 'Config → Language'
        opens = ('Драйвер монголоор нээгдэнэ. Хэрэв гарахгүй бол <b>%s → Монгол</b> '
                 'сонгоно.' % menu) if m.get('type') == 'mouse' else (
                'Драйвер шууд <b>монгол хэл дээр</b> нээгдэнэ.')

        # The language-only zip is a genuinely different, much smaller file
        # for most models - but for a few the two builds are the same
        # archive. Offering it there would promise a small file and hand
        # over the whole bundle, so it is only shown when it really differs.
        alt = ''
        if m.get('auto') and m.get('pack') and m['pack'] != m['auto']:
            alt = (
                '<p class="alt">Драйвераа аль хэдийн суулгасан бол '
                '<a href="%s">зөвхөн монгол хэлний файл</a> хангалттай — '
                'задлаад <b>install-mn.bat</b>-ыг ажиллуулна.</p>'
            ) % esc(m['pack'])

        body = (
            '<ul class="steps"><li>'
            '<div class="steptitle">Татаад суулгах</div>'
            '<div class="stephint">Драйвер болон монгол хэл хамт нэг файлд. '
            'Татсан <b>.zip</b>-ээ задлаад дотор нь байгаа <b>Суулгах.bat</b> дээр '
            'хоёр товшоод, гарч ирэх цонхон дээр Next / Install дарна.</div>'
            '%s%s'
            '<a class="btn" href="%s">%sТатаад суулгах</a>'
            '</li></ul>'
            '<div class="after">%s</div>%s'
        ) % (req('pack'), WARN_WIN, esc(m.get('auto') or m['pack']), DL, opens, alt)

    return (
        '<details class="item" id="%s" data-k="%s">'
        '<summary class="row">'
        '<span class="icon">%s</span>'
        '<span class="grow"><span class="name">%s</span><span class="sub">%s</span></span>'
        '<span class="tag">Монгол</span>%s'
        '</summary>'
        '<div class="body">%s</div>'
        '</details>'
    ) % (esc(slug(m)), esc(key(m)), icon(m),
         esc(m['brand'] + ' ' + m['name']), esc(sub), CHEV, body)


def other_row(m):
    return (
        '<a class="other" data-k="%s" href="%s" target="_blank" rel="noopener">'
        '<span class="icon">%s</span>'
        '<span class="grow"><span class="name">%s</span></span>'
        '<span class="how">%s</span>'
        '<span class="icon">%s</span>'
        '</a>'
    ) % (esc(key(m)), esc(m['vendor']), icon(m),
         esc(m['brand'] + ' ' + m['name']), esc(HOW.get(m.get('how'), '')), EXT)


def main():
    with io.open(DATA, encoding='utf-8') as fh:
        data = json.load(fh)
    with io.open(TEMPLATE, encoding='utf-8') as fh:
        html = fh.read()
    with io.open(SCRIPT, encoding='utf-8') as fh:
        script = fh.read().strip()

    # A literal "</script>" inside the inlined source would close the tag early.
    script = script.replace('</script', '<\\/script')

    ids = [slug(m) for m in data['mongolian']]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        sys.exit('duplicate model anchors: %s' % ', '.join(dupes))

    subs = {
        '<!--MN_ROWS-->': '\n'.join(mn_row(m) for m in data['mongolian']),
        '<!--OTHER_ROWS-->': '\n'.join(other_row(m) for m in data['others']),
        '<!--N_MN-->': str(len(data['mongolian'])),
        '<!--N_OTHER-->': str(len(data['others'])),
        '<!--N_TOTAL-->': str(len(data['mongolian']) + len(data['others'])),
        '<!--UPDATED-->': esc(data['updated']),
        '<!--FILTER_JS-->': script,
    }
    for token, value in subs.items():
        if token not in html:
            sys.exit('template is missing placeholder %s' % token)
        html = html.replace(token, value)

    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(html)

    size = os.path.getsize(OUT)
    print('wrote index.html  %.1f KB' % (size / 1024.0))
    print('  %d Mongolian models, %d others (%d total), all rendered server-side'
          % (len(data['mongolian']), len(data['others']),
             len(data['mongolian']) + len(data['others'])))
    no_alt = [m['name'] for m in data['mongolian']
              if m['kind'] == 'pack' and not (m.get('auto') and m.get('pack')
                                              and m['pack'] != m['auto'])]
    if no_alt:
        print('  language-only download not offered for: %s' % ', '.join(no_alt))


if __name__ == '__main__':
    main()
