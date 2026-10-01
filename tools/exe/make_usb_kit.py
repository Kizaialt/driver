#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assemble the in-shop USB kit: every one-file installer, one folder, ready to copy onto a stick.

    python tools/exe/build_exe.py            # build the exes first
    python tools/exe/make_usb_kit.py         # -> <repos folder>/Peaklab_USB_kit
    python tools/exe/make_usb_kit.py --out E:\\     # straight onto a stick

WHY A STICK: Windows warns ("Windows protected your PC") only about files that arrived through a
browser, because the browser stamps them with an internet-origin marker. A file copied from a USB
stick carries no such marker, so the installer simply opens. (Verified here: the same installer
started with no warning when unmarked, and was held behind SmartScreen when marked.)

Format the stick FAT32 or exFAT, which cannot store that marker at all, and copy the exes from the
build machine, never from a browser download. Smart App Control on a few Windows 11 PCs blocks
unsigned programs whatever their origin; for those customers use the zip from the portal.
"""
import argparse
import glob
import hashlib
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FS = os.path.join(ROOT, 'aula-fseries-mn', 'dist-exe')
KY = os.path.join(ROOT, 'kysona-m600-mn', 'dist-exe')

CUSTOMER = u"""Peaklab - Монгол хэлний суулгагч
=================================

1. Энэ USB-г компьютерт залгана.
2. Өөрийн загварын файлыг олно:
     "AULA keyboards"  - AULA гарууд
     "KYSONA mice"     - KYSONA хулганууд
3. Тэр файл дээр хоёр товшино.
4. Windows "Do you want to allow this app to make changes?" гэж асуувал "Yes" дарна.
5. Гарч ирсэн цонхонд "Үргэлжлүүлэх" дарна.
6. Дууссаны дараа драйверыг нээхэд монгол хэл дээр гарна.

Драйвер суугаагүй бол AULA/KYSONA-гийн цонх гарч ирнэ - тэнд Next / Install дарж дуусгана.
Асуудал гарвал Peaklab-д хандана уу.
"""

STAFF = u"""STAFF NOTES - not for customers
================================
Why this works: Windows only shows "Windows protected your PC" for files that came through a
browser (they carry an internet-origin marker). Files copied from a USB stick do not.

Keep it that way:
  * Format the stick FAT32 or exFAT (not NTFS). They cannot store the marker.
  * Copy the .exe files from the build machine, never from a browser download.
  * Do not zip them: unzipping re-applies the marker on some PCs.

If an installer still gets blocked on a customer's PC: Windows 11 "Smart App Control" blocks
unsigned programs regardless of where they came from. Send that customer to the zip on the
portal instead.

Every installer shows the vendor installer's SHA-256 in its setup log; SHA256SUMS.txt lists the
hash of each .exe here so a copy can be checked.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'Peaklab_USB_kit'))
    args = ap.parse_args()

    groups = [('AULA keyboards', sorted(glob.glob(os.path.join(FS, '*_mn_setup.exe')))),
              ('KYSONA mice', sorted(glob.glob(os.path.join(KY, '*_mn_setup.exe'))))]
    if not any(files for _, files in groups):
        sys.exit('no installers found - run: python tools/exe/build_exe.py')

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    lines, total = [], 0
    for folder, files in groups:
        if not files:
            continue
        dst = os.path.join(out, folder)
        os.makedirs(dst, exist_ok=True)
        for src in files:
            # AULA_F65_driver_mn_setup.exe -> "AULA F65.exe": a name a customer can read
            base = os.path.basename(src).replace('_driver_mn_setup.exe', '').replace('_', ' ')
            target = os.path.join(dst, base + '.exe')
            shutil.copyfile(src, target)
            total += os.path.getsize(target)
            lines.append('%s  %s/%s' % (sha256(target), folder, base + '.exe'))
            print('  %-16s %s  (%.1f MB)' % (folder, base + '.exe', os.path.getsize(target) / 1048576.0))

    with io.open(os.path.join(out, u'ЗААВАР.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as fh:
        fh.write(CUSTOMER)
    with io.open(os.path.join(out, 'STAFF_NOTES.txt'), 'w', encoding='utf-8', newline='\r\n') as fh:
        fh.write(STAFF)
    with io.open(os.path.join(out, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')

    print('\nkit: %s' % out)
    print('%d installers, %.0f MB in total - fits on any 1 GB stick' % (len(lines), total / 1048576.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
