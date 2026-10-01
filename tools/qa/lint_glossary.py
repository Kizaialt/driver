#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enforce one terminology policy across all four translations at once.

    python tools/qa/lint_glossary.py               # every repo found nearby
    python tools/qa/lint_glossary.py --repo ../kysona-m600-mn
    python tools/qa/lint_glossary.py --show-consistency
    python tools/qa/lint_glossary.py --self-test

The policy lives in glossary.json next to this file, and nowhere else.  The
value of the check is cross-project: a customer who sees товчлуур in the web
driver must not see товч in the desktop pack.

Three kinds of finding
----------------------
  KEEP-ENGLISH   the English source contains a product feature name that must
                 survive verbatim (Polling Rate, DKS, Rapid Trigger, ...) and
                 the Mongolian does not.  Error.

  WRONG-WORD     the Mongolian uses a word the policy rules out for that
                 concept - товч where товчлуур is required, Вэб where Хөтөч is.
                 Error.

  INCONSISTENT   the same English string is translated two different ways in
                 two different projects.  Warning: sometimes the context really
                 does differ, so a human decides.

Two traps this deliberately avoids
----------------------------------
1. Mongolian is agglutinative.  A bare substring test for "товч" matches inside
   "товчлуур", which is the word we want.  Matching is therefore token-based:
   a token counts only if stripping one known suffix leaves exactly the stem,
   and the token does not already start with the preferred word.

2. "Frequency Rate" in the .lan family is the AUDIO frequency of the
   music-reactive lighting, not a polling rate.  «Давтамж» is correct there.
   glossary.json lists it under "exempt" and the linter must never demand it
   change; --self-test asserts that.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localepack as lp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GLOSSARY = os.path.join(HERE, 'glossary.json')

MN_TOKEN = re.compile(r'[Ѐ-ӿ]+')
WORD = re.compile(r"[A-Za-z0-9.]+")


def load_glossary(path=GLOSSARY):
    with io.open(path, encoding='utf-8') as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# collecting (english, mongolian, where) triples
# --------------------------------------------------------------------------

def collect(repo_root):
    """Every English -> Mongolian pair this repo is responsible for.

    Taken from the SHIPPED artifacts where possible - that is what the customer
    reads, and it carries the vendor's real per-model English.  The hand-edited
    mn*.json files are added too, so a string that is translated but not yet
    shipped on any model is still linted.
    """
    kind = lp.repo_kind(repo_root)
    out = []                       # (english, mongolian, where)
    if kind is None or kind == 'driver':
        return kind, out

    baseline = None
    bpath = os.path.join(repo_root, 'tools', 'vendor-baseline.json')
    if os.path.isfile(bpath):
        with io.open(bpath, encoding='utf-8') as fh:
            baseline = json.load(fh)

    if kind == 'aula-driver-mn':
        data, _raw = lp.read_web_json_all(os.path.join(repo_root, 'config', 'language.json'))
        en, mn = data.get('en', {}), data.get('mn', {})
        for k, v in mn.items():
            e = en.get(k)
            if isinstance(e, str) and isinstance(v, str) and e.strip():
                out.append((e, v, 'web:%s' % k))
        return kind, out

    # pack repos: line the shipped file up with the vendor's English
    for label, path, family in lp.shipped_artifacts(repo_root, kind):
        model = lp.model_of(label)
        ref = lp.vendor_original(repo_root, family, model, kind)
        pairs = None
        if ref:
            pairs = [(e.key, e.value) for e in lp.read(ref, family).entries]
        elif baseline:
            rec = (baseline.get('models', {}).get(model)
                   or baseline.get('models', {}).get('%s:%s' % (model, family)))
            if rec and isinstance(rec.get('english'), list):
                pairs = [(k, v) for k, v in rec['english']]
        if not pairs:
            continue
        ours = lp.read(path, family).entries
        if len(ours) != len(pairs):
            continue                       # verify_artifacts.py reports this
        short = model.replace('_driver', '').replace('AULA_', '').replace('KYSONA_', '')
        for (k, e), entry in zip(pairs, ours):
            if isinstance(e, str) and isinstance(entry.value, str) and e.strip():
                out.append((e, entry.value, '%s:%s' % (short, entry.key.split('/')[-1])))

    # and the hand-edited sources, for anything not shipped on a model
    for repo_name, rel, key_is_english, _desc in lp.TRANSLATION_SOURCES:
        if repo_name != kind:
            continue
        path = os.path.join(repo_root, rel)
        if not os.path.isfile(path):
            continue
        strings, meta = lp.load_translation_source(path)
        tag = os.path.basename(rel).replace('.json', '')
        if key_is_english:
            for k, v in strings.items():
                if isinstance(v, str):
                    out.append((k, v, '%s:%s' % (tag, k[:24])))
        for ok, ov in (meta.get('_overrides') or {}).items():
            key, _sep, eng = ok.partition('|')
            if eng and isinstance(ov, str):
                out.append((eng, ov, '%s:_overrides/%s' % (tag, key)))
    return kind, out


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

def english_has(term, text):
    """Word-boundary, case-sensitive for ALL-CAPS acronyms, else case-insensitive.

    Case matters for the short ones: matching 'MT' case-insensitively would fire
    on every 'mt' inside a longer word, and 'RS' on 'rs'.
    """
    flags = 0 if term.isupper() or (len(term) <= 3 and any(c.isupper() for c in term)) \
        else re.IGNORECASE
    return re.search(r'(?<![A-Za-z0-9])%s(?![A-Za-z0-9])' % re.escape(term), text, flags)


def mongolian_uses(stem, text, preferred=None, suffixes=()):
    """True when `text` contains `stem` as a standalone word, allowing one
    Mongolian suffix - and not merely as the opening of a longer stem such as
    товчлуур, which is the word we actually want."""
    stem = stem.lower()
    pref = (preferred or '').lower()
    for tok in MN_TOKEN.findall(text.lower()):
        if pref and tok.startswith(pref):
            continue
        if not tok.startswith(stem):
            continue
        rest = tok[len(stem):]
        if rest in suffixes:
            return tok
    return None


def stem_present(stem, text):
    """Loose presence test for a required stem - agglutination means we cannot
    demand an exact form, so this is a prefix test over Cyrillic tokens."""
    stem = stem.lower()
    if ' ' in stem:
        return stem in text.lower()
    return any(tok.startswith(stem) for tok in MN_TOKEN.findall(text.lower()))


# --------------------------------------------------------------------------
# the checks
# --------------------------------------------------------------------------

def lint_pairs(pairs, gloss, require_max_words=3):
    errors, warnings = [], []
    suffixes = set(gloss.get('_suffixes', []))
    exempt = {}
    for e in gloss.get('exempt', []):
        exempt.setdefault(e['english'].strip().lower(), []).append(e)

    def is_exempt(english, where):
        # An entry may carry "only_where": ["M600"] to apply to those models
        # only - "Fire key" is a mouse button on the KYSONA but a keyboard key
        # on the F108, and the keyboard one must stay checked.
        for e in exempt.get(english.strip().lower(), []):
            scope = e.get('only_where')
            if not scope or any(str(where).startswith(s) for s in scope):
                return True
        return False

    seen = set()
    for english, mn, where in pairs:
        sig = (english, mn)
        if sig in seen:
            continue
        seen.add(sig)

        if is_exempt(english, where):
            continue

        # 1. product feature names must survive
        for rule in gloss['keep_english']:
            term = rule['term']
            if english_has(term, english) and not english_has(term, mn):
                errors.append(('KEEP-ENGLISH', where, term, english, mn, rule.get('note', '')))

        # 2/3. per-concept vocabulary
        for rule in gloss['terms']:
            if not any(english_has(w, english) for w in rule['en']):
                continue
            # A sentence that says both "key" and "button" needs both Mongolian
            # words; товч is then correct and flagging it is noise.
            if any(english_has(w, english) for w in rule.get('unless_en', [])):
                continue
            for bad in rule.get('avoid', []):
                hit = mongolian_uses(bad, mn, rule['mn'], suffixes)
                if hit:
                    errors.append(('WRONG-WORD', where,
                                   '%s -> %s (not %s; found %r)'
                                   % ('/'.join(rule['en']), rule['mn'], bad, hit),
                                   english, mn, rule.get('note', '')))
            if len(WORD.findall(english)) <= require_max_words:
                accepted = [rule['mn']] + list(rule.get('also_ok', []))
                if not any(stem_present(s, mn) for s in accepted) and lp.CYRILLIC.search(mn):
                    warnings.append(('TERM-MISSING', where,
                                     '%s -> expected %s*' % ('/'.join(rule['en']), rule['mn']),
                                     english, mn, rule.get('note', '')))
    return errors, warnings


def consistency(all_pairs):
    """Same English string, different Mongolian, in two different projects."""
    by_en = defaultdict(lambda: defaultdict(set))
    for repo, english, mn, where in all_pairs:
        key = english.strip()
        if not key or len(WORD.findall(key)) > 4:
            continue                      # sentences legitimately vary
        by_en[key][mn.strip()].add('%s/%s' % (repo, where))

    out = []
    for english, variants in by_en.items():
        if len(variants) < 2:
            continue
        repos = set()
        for places in variants.values():
            repos.update(p.split('/')[0] for p in places)
        if len(repos) < 2:
            continue                      # one project's own context switch

        # one example per repo, so the split between projects is visible
        shown = {}
        for v, places in variants.items():
            per_repo = {}
            for p in sorted(places):
                per_repo.setdefault(p.split('/')[0], p)
            shown[v] = ['%s (%s)' % (r, p.split('/', 1)[1])
                        for r, p in sorted(per_repo.items())]
        out.append((english, shown))
    return sorted(out)


# --------------------------------------------------------------------------

def self_test(gloss):
    print('SELF-TEST\n')
    suffixes = set(gloss.get('_suffixes', []))
    cases = [
        # (label, english, mongolian, expect_error_kind or None)
        ('Debounce translated away',        'Debounce',        'Товчлуурын доргилт арилгах', 'KEEP-ENGLISH'),
        ('Debounce kept',                   'Debounce Time',   'Debounce хугацаа',           None),
        ('DKS translated away',             'DKS',             'Динамик товчлуур',           'KEEP-ENGLISH'),
        ('Polling Rate kept',               'Polling Rate',    'Polling Rate',               None),
        ('key -> товч (wrong synonym)',     'Key Function',    'Товчны үүрэг',               'WRONG-WORD'),
        ('key -> товчлуур (correct)',       'Key Function',    'Товчлуурын үүрэг',           None),
        ('товчлуурын must not trip товч',   'Key',             'Товчлуур',                   None),
        ('browser -> Вэб (wrong)',          'Browser',         'Вэб хандалт',                'WRONG-WORD'),
        ('browser -> Хөтөч (correct)',      'Browser',         'Хөтчийн хандалт',            None),
        ('Frequency Rate stays Давтамж',    'Frequency Rate',  'Давтамж',                    None),
        ('Frequency stays Давтамж',         'Frequency',       'Давтамж',                    None),
        ('MT must not fire inside a word',  'Format the text', 'Текстийг хэлбэржүүлэх',      None),
        ('RS must not fire inside a word',  'Reverse',         'Эсрэгээр',                   None),
    ]
    bad = 0
    for label, english, mn, expect in cases:
        errs, _warn = lint_pairs([(english, mn, 'test')], gloss)
        kinds = {e[0] for e in errs}
        ok = (expect in kinds) if expect else not kinds
        if not ok:
            bad += 1
        print('  %-7s %-34s  expected %-12s got %s'
              % ('ok' if ok else 'BROKEN', label, expect or 'clean',
                 ', '.join(sorted(kinds)) or 'clean'))

    # the agglutination trap, directly
    assert mongolian_uses('товч', 'Товчлуурын үүрэг', 'товчлуур', suffixes) is None
    assert mongolian_uses('товч', 'Товчны үүрэг', 'товчлуур', suffixes) == 'товчны'
    print('\n  agglutination guard: товчлуурын passes, товчны is caught')
    print('\n%d of %d cases behaved wrongly.' % (bad, len(cases)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', action='append', default=[])
    ap.add_argument('--glossary', default=GLOSSARY)
    ap.add_argument('--show-consistency', action='store_true',
                    help='list every cross-project divergence, not just the count')
    ap.add_argument('--warnings', action='store_true',
                    help='also print the advisory TERM-MISSING findings')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    gloss = load_glossary(args.glossary)
    if args.self_test:
        return self_test(gloss)

    repos = list(args.repo)
    if not repos:
        for name in ('aula-driver-mn', 'aula-fseries-mn', 'kysona-m600-mn'):
            found = lp.find_sibling(name)
            if found:
                repos.append(found)

    all_pairs, n_err, n_warn = [], 0, 0
    for repo in repos:
        repo = os.path.abspath(repo)
        kind, pairs = collect(repo)
        if not pairs:
            print('\n== %s   no translation pairs found' % repo)
            continue
        errors, warnings = lint_pairs(pairs, gloss)
        all_pairs.extend((kind, e, m, w) for e, m, w in pairs)

        print('\n== %s   %d string pair(s)' % (kind, len(pairs)))
        for kindname, where, what, english, mn, note in errors:
            print('   %-13s %s' % (kindname, where))
            print('        rule    %s' % what)
            print('        EN      %s' % english[:110])
            print('        MN      %s' % mn[:110])
            if note:
                print('        policy  %s' % note.split('. ')[0])
        if args.warnings:
            for kindname, where, what, english, mn, _note in warnings:
                print('   %-13s %-26s %-38s -> %s'
                      % (kindname, where, english[:38], mn[:44]))
        print('   %d error(s), %d advisory warning(s)' % (len(errors), len(warnings)))
        n_err += len(errors)
        n_warn += len(warnings)

    div = consistency(all_pairs)
    print('\n== cross-project consistency')
    if len(set(p[0] for p in all_pairs)) < 2:
        print('   only one project in scope - run without --repo to compare all of them')
    else:
        print('   %d English string(s) translated differently in different projects' % len(div))
        show = div if args.show_consistency else div[:12]
        for english, variants in show:
            print('   "%s"' % english)
            for mn, places in sorted(variants.items()):
                print('        %-46s %s' % (mn[:46], ', '.join(places)))
        if not args.show_consistency and len(div) > len(show):
            print('   ... %d more, use --show-consistency' % (len(div) - len(show)))

    print('\n%s  -  %d error(s), %d advisory warning(s), %d cross-project divergence(s)'
          % ('GLOSSARY CLEAN' if not n_err else 'POLICY VIOLATIONS',
             n_err, n_warn, len(div)))
    return 1 if n_err else 0


if __name__ == '__main__':
    sys.exit(main())
