# Peaklab Driver Portal

One page where a Peaklab customer finds the driver for the exact keyboard or
mouse they just bought, and gets it working in Mongolian.

Live: <https://kizaialt.github.io/driver/>

## Register

**product** — this is a tool, not a campaign. The customer arrives with a task
("my new keyboard's software is in English and I can't read it"), and the page
succeeds when it disappears into that task. No hero, no pitch, no scroll story.

## Users & Purpose

**Who:** Mongolian customers who just bought a mechanical keyboard or gaming
mouse from Peaklab. Mostly gamers, teens to thirties. Comfortable with games,
not necessarily with English, and definitely not with hunting through a Chinese
vendor's download page.

**Context of use:** two moments, both hostile to fuss.
1. **In the shop, on a phone**, scanning a QR on the box or counter while a
   staff member watches. Cheap Android, one hand, maybe bad light.
2. **At home on a laptop**, an hour after unboxing, mildly frustrated that the
   software they downloaded is in Chinese.

**The job:** *"I have this exact model. Tell me what to click, in my language."*

Success is measured in seconds-to-correct-download, not time-on-page. A
customer who leaves in 40 seconds with the right file is the win condition.

**Failure modes to design against:**
- Customer can't tell which of F75 / F75 MAX / F75HE they own.
- Customer downloads our language pack without the vendor driver, and nothing
  happens.
- Customer's model isn't one of the seven we translated and they hit a dead end.

## Brand & Personality

**Three words:** plain, certain, quick.

This is a shop's support desk in web form. Its authority comes from being
obviously correct and current, not from looking expensive. The most premium
thing it can do is answer in one screen.

Peaklab's existing surfaces (restaurant-QR, Peakpoint QR, ChatShop) share a
Cal.com-derived system: white canvas, near-black primary actions, Inter
throughout, generous spacing, 8/12px radii. This page inherits that. Identity
preservation beats novelty; a customer who has seen any other Peaklab page
should recognise this one.

**Mongolian typography:** Inter for everything. Its `cyrillic-ext` subset covers
Өө/Үү correctly. Not "Noto Sans Mongolian" — that font targets the classical
vertical script, not the Cyrillic Mongolian people actually write.

## Anti-references

- **Gamer-peripheral aesthetic.** Black background, neon cyan/magenta, angular
  clip-paths, "RGB" everywhere. It's the obvious answer for a keyboard shop and
  therefore the wrong one; it also destroys readability for the older customer
  buying a keyboard for their kid.
- **SaaS landing page.** Hero headline, three benefit cards, stat row, CTA
  band. There is nothing to sell here — they already bought the keyboard.
- **A wall of links.** The lazy version of this page is a `<ul>` of 50 model
  names. That's a directory, not an answer.

## Design principles

1. **The model name is the interface.** Everything is subordinate to "find my
   model". Search is the primary control and takes focus on desktop.
2. **Never leave a customer with nothing.** Every model we know of appears,
   even the ones with no Mongolian, with the official vendor driver as the
   fallback. Silence is worse than an English link.
3. **State the two-step honestly.** For language-pack models, the vendor driver
   must be installed first. The page must make that ordering impossible to miss,
   because getting it wrong is the #1 predictable support call.
4. **Never overstate.** The packs are not yet verified on real hardware. The
   page says so plainly rather than implying a polish we haven't earned.

## Accessibility

- Mobile-first, single column to ~700px. Thumb-reachable tap targets (44px).
- Body text ≥4.5:1 contrast. No light-gray-on-white "elegance".
- Works with no JavaScript for the core content (search is an enhancement).
- Fast on a slow connection: single HTML file, no framework, no web fonts
  blocking first paint.
