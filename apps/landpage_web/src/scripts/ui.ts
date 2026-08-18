export function initUi() {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reduce = reducedMotion.matches;

  if (!reduce) {
    const segmenter =
      typeof Intl.Segmenter === 'function'
        ? new Intl.Segmenter(document.documentElement.lang, { granularity: 'grapheme' })
        : null;
    const combiningMark = /\p{Mark}/u;
    const splitGraphemes = (value: string) => {
      if (segmenter) return Array.from(segmenter.segment(value), ({ segment }) => segment);
      return Array.from(value).reduce<string[]>((graphemes, character) => {
        if (combiningMark.test(character) && graphemes.length > 0) {
          graphemes[graphemes.length - 1] += character;
        } else {
          graphemes.push(character);
        }
        return graphemes;
      }, []);
    };

    document.querySelectorAll<HTMLElement>('[data-typewriter]').forEach((typewriter) => {
      const output = typewriter.querySelector<HTMLElement>('[data-typewriter-text]');
      const container = typewriter.closest<HTMLElement>('[data-typewriter-container]');
      const toggle = container?.querySelector<HTMLButtonElement>('[data-typewriter-toggle]');
      if (!output) return;

      let phrases: string[] = [];
      try {
        const parsed = JSON.parse(typewriter.dataset.phrases ?? '[]');
        if (Array.isArray(parsed)) {
          phrases = parsed.filter((phrase): phrase is string => typeof phrase === 'string' && phrase.length > 0);
        }
      } catch {
        return;
      }
      if (phrases.length < 2) return;
      typewriter.classList.add('is-active');
      toggle?.classList.add('is-ready');

      let paused = false;
      let stopped = false;
      const wait = async (duration: number) => {
        let remaining = duration;
        while (remaining > 0 && !stopped) {
          const interval = Math.min(remaining, 80);
          await new Promise<void>((resolve) => window.setTimeout(resolve, interval));
          if (!paused && !document.hidden) remaining -= interval;
        }
      };

      const syncToggle = () => {
        if (!toggle) return;
        const pauseIcon = toggle.querySelector<SVGElement>('[data-typewriter-pause]');
        const playIcon = toggle.querySelector<SVGElement>('[data-typewriter-play]');
        toggle.setAttribute(
          'aria-label',
          toggle.getAttribute(paused ? 'data-resume-label' : 'data-pause-label') ?? '',
        );
        pauseIcon?.classList.toggle('is-hidden', paused);
        playIcon?.classList.toggle('is-hidden', !paused);
        typewriter.classList.toggle('is-paused', paused);
      };

      toggle?.addEventListener('click', () => {
        paused = !paused;
        syncToggle();
      });

      reducedMotion.addEventListener('change', (event) => {
        if (!event.matches) return;
        stopped = true;
        paused = false;
        output.textContent = phrases[0];
        typewriter.classList.remove('is-active', 'is-paused');
        toggle?.classList.remove('is-ready');
      });

      const rotate = async () => {
        let phraseIndex = 0;
        await wait(1900);

        while (true) {
          const current = splitGraphemes(phrases[phraseIndex]);
          for (let length = current.length - 1; length >= 0; length -= 1) {
            if (stopped) return;
            output.textContent = current.slice(0, length).join('');
            await wait(30);
          }

          phraseIndex = (phraseIndex + 1) % phrases.length;
          const next = splitGraphemes(phrases[phraseIndex]);
          for (let length = 1; length <= next.length; length += 1) {
            if (stopped) return;
            output.textContent = next.slice(0, length).join('');
            await wait(58);
          }

          await wait(1900);
        }
      };

      syncToggle();
      void rotate();
    });
  }

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
