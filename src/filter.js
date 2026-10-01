(function () {
  'use strict';
  /* Rows are already in the served HTML; this script only filters them.
     With JavaScript off the full catalogue is still there, just unfiltered. */

  var q = document.getElementById('q');
  var clear = document.getElementById('clear');
  var count = document.getElementById('count');
  var empty = document.getElementById('empty');
  var secMn = document.getElementById('sec-mn');
  var secOther = document.getElementById('sec-other');

  var T = {
    all: 'загвар',
    none: 'Олдсонгүй',
    found: 'загвар олдлоо'
  };

  /* ---------------------------------------------------------------- search
     Mongolian Cyrillic -> Latin, phonetically, the way people actually write
     model names ("вин 60" for WIN 60, "ф75" for F75, "кисона" for KYSONA).
     The SAME transform runs over the query and over every row key, so the
     two meet in the middle: a customer typing on a Cyrillic keyboard finds a
     Latin model name without us hand-writing an alias for every spelling. */
  var CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'j', 'з': 'z', 'и': 'i', 'й': 'i', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'ө': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ү': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh',
    'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
  };

  function norm(s) {
    s = String(s).toLowerCase();
    var out = '', i, ch;
    for (i = 0; i < s.length; i++) {
      ch = s.charAt(i);
      out += CYR.hasOwnProperty(ch) ? CYR[ch] : ch;
    }
    /* Everything that is not a letter or digit becomes a gap, so "F-75",
       "F 75" and "F75" all reduce to comparable text. */
    return out.replace(/[^a-z0-9]+/g, ' ').replace(/^ | $/g, '');
  }

  /* Second form with the gaps removed, so "WIN60HE" typed without spaces
     still matches "AULA WIN 60 HE". */
  function tight(s) { return s.replace(/ /g, ''); }

  var rows = [].slice.call(document.querySelectorAll('[data-k]')).map(function (el) {
    var k = norm(el.getAttribute('data-k'));
    return { el: el, k: k, t: tight(k), mn: el.tagName === 'DETAILS' };
  });
  var total = rows.length;

  /* Only ever auto-close a row we auto-opened; never one the user opened. */
  var autoOpened = null;

  function filter() {
    var term = norm(q.value);
    clear.style.display = q.value ? 'grid' : 'none';

    if (!term) {
      rows.forEach(function (r) { r.el.hidden = false; });
      secMn.hidden = false;
      secOther.hidden = false;
      empty.classList.remove('show');
      count.textContent = total + ' ' + T.all;
      return;
    }

    var tt = tight(term);
    var shown = 0, shownMn = 0, lastMn = null;
    rows.forEach(function (r) {
      var hit = r.k.indexOf(term) !== -1 || r.t.indexOf(tt) !== -1;
      r.el.hidden = !hit;
      if (hit) {
        shown++;
        if (r.mn) { shownMn++; lastMn = r.el; }
      }
    });

    secMn.hidden = shownMn === 0;
    secOther.hidden = (shown - shownMn) === 0;
    empty.classList.toggle('show', shown === 0);
    count.textContent = shown === 0 ? T.none : shown + ' ' + T.found;

    /* exactly one Mongolian match: open it, since that is the answer */
    if (autoOpened && autoOpened !== lastMn) { autoOpened.open = false; autoOpened = null; }
    if (shownMn === 1 && lastMn && !lastMn.open) { lastMn.open = true; autoOpened = lastMn; }
  }

  q.addEventListener('input', filter);
  clear.addEventListener('click', function () { q.value = ''; filter(); q.focus(); });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && q.value) { q.value = ''; filter(); }
  });

  /* A fuller prompt only where there is room for it; the short default in
     the markup is the one a 375px phone can actually display. */
  if (q.dataset.phWide && window.matchMedia('(min-width:560px)').matches) {
    q.placeholder = q.dataset.phWide;
  }

  /* Desktop only. On touch this pops the keyboard over the list on arrival. */
  if (window.matchMedia('(min-width:700px)').matches && !('ontouchstart' in window)) {
    q.focus();
  }

  filter();

  /* ------------------------------------------------------- deep links
     Each model row has an id, so a link can point at one exact model.
     Shop staff can send a customer straight to their keyboard, and the
     share button below hands over whatever the customer is looking at. */
  var bar = document.getElementById('searchbar');

  /* Park a jumped-to row clear of the sticky bar rather than under it.
     Measured, because the bar's height moves with the user's font size. */
  function measureBar() {
    document.documentElement.style.setProperty(
      '--barh', (bar.offsetHeight + 12) + 'px');
  }
  measureBar();
  window.addEventListener('resize', measureBar);

  function openHash() {
    var id = decodeURIComponent((location.hash || '').slice(1));
    if (!id) return;
    var el = document.getElementById(id);
    if (el && el.tagName === 'DETAILS') {
      el.open = true;
      el.scrollIntoView({ block: 'start' });
    }
  }
  openHash();
  window.addEventListener('hashchange', openHash);

  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d || d.tagName !== 'DETAILS' || !d.id) return;
    if (d.open && d !== autoOpened && history.replaceState) {
      history.replaceState(null, '', '#' + d.id);
    }
  }, true);

  /* ------------------------------------------------------- share the link
     The commonest arrival is a phone, in the shop, scanning a QR - and
     nothing on this page can be finished on a phone. The one useful thing
     we can offer there is getting this URL onto their computer. */
  var send = document.getElementById('sendlink');
  if (send) {
    var label = send.querySelector('.lbl');
    var canShare = typeof navigator.share === 'function';
    if (canShare) label.textContent = 'Холбоосыг илгээх';

    send.addEventListener('click', function () {
      var url = location.href;
      function done(text) {
        var was = label.textContent;
        label.textContent = text;
        setTimeout(function () { label.textContent = was; }, 2400);
      }
      if (canShare) {
        navigator.share({ title: document.title, url: url }).catch(function () {});
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(
          function () { done('Хуулагдлаа'); },
          function () { done(url); }
        );
        return;
      }
      done(url);
    });
  }

  /* Hairline under the sticky bar only once it is actually stuck. */
  var sentinel = document.createElement('div');
  bar.parentNode.insertBefore(sentinel, bar);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (e) {
      bar.classList.toggle('is-stuck', !e[0].isIntersecting);
    }).observe(sentinel);
  }
})();
