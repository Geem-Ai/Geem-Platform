export function initUi() {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const header = document.querySelector<HTMLElement>('[data-site-header]');
  if (header) {
    const onScroll = () => {
      header.classList.toggle('is-scrolled', window.scrollY > 12);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  const menuButton = document.querySelector<HTMLButtonElement>('[data-menu-button]');
  const menu = document.querySelector<HTMLDialogElement>('[data-mobile-menu]');
  if (menuButton && menu) {
    const openLabel = menuButton.getAttribute('aria-label') ?? '';
    const closeLabel = menuButton.getAttribute('data-close-label') ?? openLabel;
    const sync = () => {
      menuButton.setAttribute('aria-expanded', menu.open ? 'true' : 'false');
      menuButton.setAttribute('aria-label', menu.open ? closeLabel : openLabel);
    };
    menuButton.addEventListener('click', () => {
      if (menu.open) menu.close();
      else menu.showModal();
      sync();
    });
    menu.addEventListener('close', sync);
    menu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => menu.close());
    });
  }

  if (!reduce) {
    const revealables = document.querySelectorAll<HTMLElement>('[data-reveal], [data-reveal-stagger]');
    if (revealables.length && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            entry.target.classList.add('is-visible');
            if (entry.target.hasAttribute('data-draw')) {
              entry.target.classList.add('is-drawn');
            }
            observer.unobserve(entry.target);
          }
        },
        { threshold: 0.16, rootMargin: '0px 0px -8% 0px' },
      );
      revealables.forEach((el) => observer.observe(el));
    } else {
      revealables.forEach((el) => el.classList.add('is-visible', 'is-drawn'));
    }

    document.querySelectorAll<HTMLElement>('[data-draw]').forEach((el) => {
      if (!el.hasAttribute('data-reveal') && !el.hasAttribute('data-reveal-stagger')) {
        const observer = new IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              if (!entry.isIntersecting) continue;
              entry.target.classList.add('is-drawn');
              observer.unobserve(entry.target);
            }
          },
          { threshold: 0.2 },
        );
        observer.observe(el);
      }
    });
  } else {
    document
      .querySelectorAll('[data-reveal], [data-reveal-stagger], [data-draw]')
      .forEach((el) => el.classList.add('is-visible', 'is-drawn'));
  }

  document.querySelectorAll<HTMLButtonElement>('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const targetId = button.getAttribute('data-copy');
      const target = targetId ? document.getElementById(targetId) : null;
      if (!target) return;
      const text = target.textContent ?? '';
      try {
        await navigator.clipboard.writeText(text);
        const original = button.textContent;
        button.textContent = button.getAttribute('data-copied-label') || 'Copied';
        window.setTimeout(() => {
          button.textContent = original;
        }, 1600);
      } catch {
        /* ignore */
      }
    });
  });
}

initUi();
