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
  var rows = [].slice.call(document.querySelectorAll('[data-k]'));
  var total = rows.length;

  var T = {
    all: 'загвар',                       // загвар
    none: 'Олдсонгүй',    // Олдсонгүй
    found: 'загвар олдлоо' // загвар олдлоо
  };

  function norm(s) { return s.toLowerCase().replace(/\s+/g, ' ').trim(); }

  function filter() {
    var term = norm(q.value);
    clear.style.display = term ? 'grid' : 'none';

    if (!term) {
      rows.forEach(function (r) { r.hidden = false; });
      secMn.hidden = false;
      secOther.hidden = false;
      empty.classList.remove('show');
      count.textContent = total + ' ' + T.all;
      return;
    }

    var shown = 0, shownMn = 0, lastMn = null;
    rows.forEach(function (r) {
      var hit = r.getAttribute('data-k').indexOf(term) !== -1;
      r.hidden = !hit;
      if (hit) {
        shown++;
        if (r.tagName === 'DETAILS') { shownMn++; lastMn = r; }
      }
    });

    secMn.hidden = shownMn === 0;
    secOther.hidden = (shown - shownMn) === 0;
    empty.classList.toggle('show', shown === 0);
    count.textContent = shown === 0 ? T.none : shown + ' ' + T.found;

    /* exactly one Mongolian match: open it, since that is the answer */
    if (shownMn === 1 && lastMn) lastMn.open = true;
  }

  q.addEventListener('input', filter);
  clear.addEventListener('click', function () { q.value = ''; filter(); q.focus(); });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && q.value) { q.value = ''; filter(); }
  });

  /* Desktop only. On touch this pops the keyboard over the list on arrival. */
  if (window.matchMedia('(min-width:700px)').matches && !('ontouchstart' in window)) {
    q.focus();
  }

  filter();

  /* Hairline under the sticky bar only once it is actually stuck. */
  var bar = document.getElementById('searchbar');
  var sentinel = document.createElement('div');
  bar.parentNode.insertBefore(sentinel, bar);
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (e) {
      bar.classList.toggle('is-stuck', !e[0].isIntersecting);
    }).observe(sentinel);
  }
})();
