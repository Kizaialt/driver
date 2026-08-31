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
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, 'src', 'index.template.html')
DATA = os.path.join(ROOT, 'data', 'models.json')
OUT = os.path.join(ROOT, 'index.html')

ICON = {
    'kb': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M8 14h8" stroke-linecap="round"/></svg>',
    'mouse': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 6v4" stroke-linecap="round"/></svg>',
}
CHEV = '<svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>'
DL = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/></svg>'
EXT = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v6H4V6h6"/></svg>'

HOW = {'web': 'Онлайн драйвер', 'exe': 'Windows программ', 'hub': 'AULA HUB программ'}


def esc(s):
    return (str(s if s is not None else '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def key(m):
    parts = [m.get('brand', ''), m.get('name', '')] + m.get('alias', []) + [m.get('note', '')]
    return ' '.join(' '.join(parts).lower().split())


def icon(m):
    return ICON.get(m.get('type'), ICON['kb'])


def mn_row(m):
    sub = m.get('note') or ('Хулгана' if m.get('type') == 'mouse' else 'Гар')

    if m['kind'] == 'web':
        body = (
            '<ul class="steps"><li>'
            '<div class="steptitle">Онлайн драйверыг нээх</div>'
            '<div class="stephint">Юу ч суулгах шаардлагагүй. Chrome эсвэл Edge хөтчөөр '
            'нээгээд гараа USB-ээр залгана.</div>'
            '<a class="btn" href="%s" target="_blank" rel="noopener">%sДрайвер нээх</a>'
            '</li></ul>'
            '<div class="after">Гар холбогдоод шууд монголоор нээгдэнэ. '
            'Firefox, Safari дээр ажиллахгүй.</div>'
        ) % (esc(m['web']), EXT)
    else:
        # Step 1 carries the primary button on purpose: installing only the
        # language pack, without the vendor driver, is the most likely way a
        # customer gets stuck.
        menu = 'Setting → Language' if m.get('type') == 'mouse' else 'Config → Language'
        body = (
            '<ul class="steps">'
            '<li>'
            '<div class="steptitle">Үйлдвэрлэгчийн драйверыг суулгах</div>'
            '<div class="stephint">%s-гийн жинхэнэ драйвер. <b>Үүнийг заавал эхэлж '
            'суулгана</b> — эс тэгвээс монгол хэл ажиллахгүй.</div>'
            '<a class="btn" href="%s" target="_blank" rel="noopener">%sДрайвер татах</a>'
            '</li>'
            '<li>'
            '<div class="steptitle">Монгол хэлний багцыг нэмэх</div>'
            '<div class="stephint">Задлаад <b>install-mn.bat</b> дээр хоёр товшино. '
            'Администратор эрх асуувал зөвшөөрнө.</div>'
            '<a class="btn ghost" href="%s">%sМонгол багц татах</a>'
            '</li>'
            '</ul>'
            '<div class="after">Дараа нь драйвераа нээгээд <b>%s → Монгол</b> сонгоно.</div>'
        ) % (esc(m['brand']), esc(m['vendor']), DL, esc(m['pack']), DL, menu)

    return (
        '<details class="item" data-k="%s">'
        '<summary class="row">'
        '<span class="icon">%s</span>'
        '<span class="grow"><span class="name">%s</span><span class="sub">%s</span></span>'
        '<span class="tag">Монгол</span>%s'
        '</summary>'
        '<div class="body">%s</div>'
        '</details>'
    ) % (esc(key(m)), icon(m), esc(m['brand'] + ' ' + m['name']), esc(sub), CHEV, body)


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

    subs = {
        '<!--MN_ROWS-->': '\n'.join(mn_row(m) for m in data['mongolian']),
        '<!--OTHER_ROWS-->': '\n'.join(other_row(m) for m in data['others']),
        '<!--N_MN-->': str(len(data['mongolian'])),
        '<!--N_OTHER-->': str(len(data['others'])),
        '<!--N_TOTAL-->': str(len(data['mongolian']) + len(data['others'])),
        '<!--UPDATED-->': esc(data['updated']),
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


if __name__ == '__main__':
    main()
