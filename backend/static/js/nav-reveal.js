/* Adds `.is-revealed` to `.top-nav` once the hero fully scrolls out of view.
   `.top-nav` is `position: sticky; top: 0` in CSS — the JS only gates the
   entrance shadow so the nav doesn't announce itself while it's still
   flowing below the hero. Bail silently if either element is missing. */
(() => {
  const hero = document.querySelector('.hero');
  const nav = document.querySelector('.top-nav');
  if (!hero || !nav || typeof IntersectionObserver === 'undefined') return;

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        nav.classList.toggle('is-revealed', !entry.isIntersecting);
      }
    },
    { threshold: 0 },
  );
  observer.observe(hero);
})();
