import { marked } from 'marked';
import DOMPurify from 'dompurify';

type Bootstrap = {
  widget_id: string;
  title: string;
  subtitle: string | null;
  greeting: string | null;
  logo_url: string | null;
  locale: string;
  position: string;
  primary_color: string;
  text_color: string;
};

type MessageOut = {
  answer: string;
  session_id?: string | null;
};

const THINKING_EN = [
  'Geem is thinking…',
  'Checking sources…',
  'Gathering context…',
  'Reading your knowledge…',
  'Preparing an answer…',
  'Looking that up…',
];

const THINKING_AR = [
  'Geem يفكر…',
  'جارٍ التحقق من المصادر…',
  'جارٍ جمع السياق…',
  'جارٍ قراءة معرفتك…',
  'جارٍ تجهيز الإجابة…',
  'جارٍ البحث عن المعلومة…',
];

const CHAR_MS = 28;
const HOLD_MS = 1600;
const DELETE_MS = 16;
const BETWEEN_MS = 280;

function currentScript(): HTMLScriptElement | null {
  const script = document.currentScript;
  if (script instanceof HTMLScriptElement) return script;
  const scripts = document.querySelectorAll('script[data-widget-id]');
  return (scripts[scripts.length - 1] as HTMLScriptElement) || null;
}

function apiBase(script: HTMLScriptElement): string {
  const override = script.getAttribute('data-api-base');
  if (override) return override.replace(/\/$/, '');
  try {
    return new URL(script.src).origin;
  } catch {
    return window.location.origin;
  }
}

function shuffle<T>(items: readonly T[]): T[] {
  const pool = [...items];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = pool[i]!;
    pool[i] = pool[j]!;
    pool[j] = tmp;
  }
  return pool;
}

function prefersReducedMotion(): boolean {
  return Boolean(
    window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
}

marked.setOptions({
  gfm: true,
  breaks: true,
});

function renderMarkdown(content: string): string {
  const raw = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ['target', 'rel'],
  });
}

function css(): string {
  return `
.geem-widget-root{all:initial;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.geem-widget-root *{box-sizing:border-box}
.geem-launcher{position:fixed;z-index:2147483000;width:60px;height:60px;border-radius:999px;border:none;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.22);display:flex;align-items:center;justify-content:center;padding:0;overflow:hidden;background:#fff}
.geem-launcher-mascot{pointer-events:none;display:block;width:46px;height:46px;max-width:100%;max-height:100%}
.geem-launcher-mascot object,.geem-launcher-mascot img{pointer-events:none;display:block;width:100%;height:100%;object-fit:contain;object-position:center bottom}
.geem-panel{position:fixed;z-index:2147483000;width:min(380px,calc(100vw - 24px));height:min(560px,calc(100vh - 100px));border-radius:16px;overflow:hidden;display:none;flex-direction:column;box-shadow:0 16px 48px rgba(0,0,0,.28);background:#fff;color:#111}
.geem-panel.is-open{display:flex}
.geem-header{padding:14px 16px;display:flex;gap:10px;align-items:center}
.geem-header img{width:36px;height:36px;border-radius:8px;object-fit:cover;background:rgba(255,255,255,.15)}
.geem-header h1{margin:0;font-size:15px;font-weight:700;line-height:1.2}
.geem-header p{margin:2px 0 0;font-size:12px;opacity:.85}
.geem-messages{flex:1;overflow:auto;padding:14px;background:#f6f7f9;display:flex;flex-direction:column;gap:10px}
.geem-bubble{max-width:90%;padding:10px 12px;border-radius:12px;font-size:14px;line-height:1.55;word-break:break-word}
.geem-bubble.bot{align-self:flex-start;background:#fff;border:1px solid #e6e8ec;color:#374151;white-space:normal}
.geem-bubble.user{align-self:flex-end;color:#fff;white-space:pre-wrap}
.geem-bubble.thinking{color:#6b7280;white-space:pre-wrap}
.geem-md{margin:0}
.geem-md>*:first-child{margin-top:0!important}
.geem-md>*:last-child{margin-bottom:0!important}
.geem-md p{margin:0.55em 0;line-height:1.55}
.geem-md h1,.geem-md h2,.geem-md h3,.geem-md h4{margin:0.75em 0 0.4em;font-weight:700;line-height:1.3;color:#111}
.geem-md h1{font-size:1.2em}
.geem-md h2{font-size:1.1em}
.geem-md h3{font-size:1.05em}
.geem-md ul,.geem-md ol{margin:0.55em 0;padding-inline-start:1.35em}
.geem-md li{margin:0.3em 0}
.geem-md li>p{margin:0.2em 0}
.geem-md a{color:#0e2f44;text-decoration:underline;word-break:break-word}
.geem-md strong{font-weight:700}
.geem-md em{font-style:italic}
.geem-md code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:0.85em;background:#f3f4f6;padding:0.1em 0.35em;border-radius:4px}
.geem-md pre{margin:0.65em 0;padding:10px 12px;overflow-x:auto;background:#111827;color:#f9fafb;border-radius:8px;font-size:12px;line-height:1.45}
.geem-md pre code{background:transparent;padding:0;color:inherit;font-size:inherit}
.geem-md blockquote{margin:0.65em 0;padding:0.25em 0 0.25em 0.85em;border-inline-start:3px solid #d1d5db;color:#6b7280}
.geem-md hr{margin:0.85em 0;border:none;border-top:1px solid #e5e7eb}
.geem-md table{display:block;width:100%;margin:0.65em 0;overflow-x:auto;border-collapse:collapse;font-size:13px}
.geem-md th,.geem-md td{border:1px solid #e5e7eb;padding:6px 8px;text-align:start}
.geem-md th{background:#f9fafb;font-weight:600}
.geem-thinking-cursor{display:inline-block;width:1px;height:0.9em;margin-inline-start:2px;vertical-align:middle;background:currentColor;animation:geem-pulse 1s ease-in-out infinite}
@keyframes geem-pulse{0%,100%{opacity:1}50%{opacity:.25}}
.geem-composer{display:flex;align-items:center;gap:8px;padding:10px 10px 0;border-top:1px solid #e6e8ec;background:#fff}
.geem-composer input{flex:1;height:40px;border:1px solid #d7dbe3;border-radius:10px;padding:0 12px;font-size:14px;line-height:40px;outline:none;margin:0}
.geem-composer button{flex-shrink:0;height:40px;border:none;border-radius:10px;padding:0 14px;cursor:pointer;font-size:14px;font-weight:600;line-height:40px;color:#fff;margin:0}
.geem-composer button:disabled{opacity:.6;cursor:not-allowed}
.geem-footer{display:block;margin:0;padding:6px 10px;background:#fff;text-align:center;font-size:11px;line-height:1;color:#9ca3af}
.geem-footer a{color:#0e2f44;font-weight:600;text-decoration:none}
.geem-footer a:hover{text-decoration:underline}
.geem-close{margin-inline-start:auto;background:transparent;border:none;color:inherit;cursor:pointer;font-size:18px;opacity:.85}
`;
}

type ThinkingController = {
  el: HTMLElement;
  stop: () => void;
};

function startThinking(messagesEl: HTMLElement, statuses: string[]): ThinkingController {
  const el = document.createElement('div');
  el.className = 'geem-bubble bot thinking';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-live', 'polite');
  const textNode = document.createElement('span');
  const cursor = document.createElement('span');
  cursor.className = 'geem-thinking-cursor';
  cursor.setAttribute('aria-hidden', 'true');
  el.appendChild(textNode);
  el.appendChild(cursor);
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  const list = shuffle(statuses);
  let index = 0;
  let charLen = 0;
  let phase: 'typing' | 'holding' | 'deleting' | 'gap' = 'typing';
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  function clear() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function tick() {
    if (stopped || list.length === 0) return;
    const current = list[index % list.length] ?? '';

    if (prefersReducedMotion()) {
      textNode.textContent = current;
      timer = setTimeout(() => {
        index = (index + 1) % list.length;
        tick();
      }, HOLD_MS);
      return;
    }

    if (phase === 'typing') {
      if (charLen >= current.length) {
        phase = 'holding';
        timer = setTimeout(tick, 0);
        return;
      }
      charLen += 1;
      textNode.textContent = current.slice(0, charLen);
      timer = setTimeout(tick, CHAR_MS);
    } else if (phase === 'holding') {
      timer = setTimeout(() => {
        phase = list.length <= 1 ? 'holding' : 'deleting';
        tick();
      }, HOLD_MS);
    } else if (phase === 'deleting') {
      if (charLen <= 0) {
        phase = 'gap';
        timer = setTimeout(tick, 0);
        return;
      }
      charLen -= 1;
      textNode.textContent = current.slice(0, charLen);
      timer = setTimeout(tick, DELETE_MS);
    } else {
      timer = setTimeout(() => {
        index = (index + 1) % list.length;
        charLen = 0;
        phase = 'typing';
        tick();
      }, BETWEEN_MS);
    }
  }

  tick();

  return {
    el,
    stop: () => {
      stopped = true;
      clear();
      el.remove();
    },
  };
}

async function boot() {
  const script = currentScript();
  if (!script) return;
  const widgetId = script.getAttribute('data-widget-id');
  if (!widgetId) {
    console.error('[Geem Widget] missing data-widget-id');
    return;
  }
  const base = apiBase(script);
  const localeAttr = script.getAttribute('data-locale');

  let bootstrap: Bootstrap;
  try {
    const res = await fetch(`${base}/api/public/widgets/${widgetId}/bootstrap`, {
      credentials: 'omit',
    });
    if (!res.ok) throw new Error(`bootstrap ${res.status}`);
    bootstrap = (await res.json()) as Bootstrap;
  } catch (err) {
    console.error('[Geem Widget] failed to bootstrap', err);
    return;
  }

  const locale = (localeAttr || bootstrap.locale || 'ar').toLowerCase();
  const rtl = locale.startsWith('ar');
  const primary = bootstrap.primary_color || '#0e2f44';
  const text = bootstrap.text_color || '#f2f2f2';
  const side = bootstrap.position === 'bottom-left' ? 'left' : 'right';
  const thinkingStatuses = rtl ? THINKING_AR : THINKING_EN;

  const style = document.createElement('style');
  style.textContent = css();
  document.head.appendChild(style);

  const root = document.createElement('div');
  root.className = 'geem-widget-root';
  root.setAttribute('dir', rtl ? 'rtl' : 'ltr');
  document.body.appendChild(root);

  // Closed by default: only the launcher is visible until the visitor opens it.
  const launcher = document.createElement('button');
  launcher.type = 'button';
  launcher.className = 'geem-launcher';
  launcher.style.bottom = '20px';
  launcher.style[side] = '20px';
  launcher.setAttribute('aria-label', rtl ? 'فتح المحادثة' : 'Open chat');
  launcher.setAttribute('aria-expanded', 'false');
  launcher.setAttribute('aria-controls', 'geem-widget-panel');

  const mascotWrap = document.createElement('span');
  mascotWrap.className = 'geem-launcher-mascot';
  mascotWrap.setAttribute('data-geem-mascot', 'animated');
  const mascot = document.createElement('object');
  mascot.type = 'image/svg+xml';
  mascot.data = `${base}/geem-animated.svg`;
  mascot.setAttribute('aria-hidden', 'true');
  mascot.tabIndex = -1;
  const mascotFallback = document.createElement('img');
  mascotFallback.src = `${base}/geem-animated.svg`;
  mascotFallback.alt = '';
  mascot.appendChild(mascotFallback);
  mascotWrap.appendChild(mascot);
  launcher.appendChild(mascotWrap);
  root.appendChild(launcher);

  const panel = document.createElement('div');
  panel.id = 'geem-widget-panel';
  panel.className = 'geem-panel';
  panel.style.bottom = '88px';
  panel.style[side] = '20px';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'false');
  panel.setAttribute('aria-label', bootstrap.title || 'Geem');

  const header = document.createElement('div');
  header.className = 'geem-header';
  header.style.background = primary;
  header.style.color = text;
  if (bootstrap.logo_url) {
    const img = document.createElement('img');
    img.src = bootstrap.logo_url;
    img.alt = '';
    header.appendChild(img);
  }
  const titles = document.createElement('div');
  const h1 = document.createElement('h1');
  h1.textContent = bootstrap.title || 'Geem';
  titles.appendChild(h1);
  if (bootstrap.subtitle) {
    const p = document.createElement('p');
    p.textContent = bootstrap.subtitle;
    titles.appendChild(p);
  }
  header.appendChild(titles);
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'geem-close';
  closeBtn.setAttribute('aria-label', rtl ? 'إغلاق' : 'Close');
  closeBtn.textContent = '×';
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const messages = document.createElement('div');
  messages.className = 'geem-messages';
  panel.appendChild(messages);

  function addBubble(textContent: string, kind: 'bot' | 'user') {
    const el = document.createElement('div');
    el.className = `geem-bubble ${kind}`;
    if (kind === 'user') {
      el.style.background = primary;
      el.textContent = textContent;
    } else {
      const md = document.createElement('div');
      md.className = 'geem-md';
      md.innerHTML = renderMarkdown(textContent);
      md.querySelectorAll('a[href]').forEach((anchor) => {
        anchor.setAttribute('target', '_blank');
        anchor.setAttribute('rel', 'noopener noreferrer');
      });
      el.appendChild(md);
    }
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  if (bootstrap.greeting) addBubble(bootstrap.greeting, 'bot');

  const composer = document.createElement('form');
  composer.className = 'geem-composer';
  const input = document.createElement('input');
  input.type = 'text';
  input.autocomplete = 'off';
  input.placeholder = rtl ? 'اكتب رسالتك…' : 'Type a message…';
  const send = document.createElement('button');
  send.type = 'submit';
  send.textContent = rtl ? 'إرسال' : 'Send';
  send.style.background = primary;
  composer.appendChild(input);
  composer.appendChild(send);
  panel.appendChild(composer);

  const footer = document.createElement('div');
  footer.className = 'geem-footer';
  const poweredPrefix = document.createTextNode(
    rtl ? 'مدعوم بواسطة ' : 'Powered by ',
  );
  const poweredLink = document.createElement('a');
  poweredLink.href = 'https://geem.ai';
  poweredLink.target = '_blank';
  poweredLink.rel = 'noopener noreferrer';
  poweredLink.textContent = 'Geem';
  footer.appendChild(poweredPrefix);
  footer.appendChild(poweredLink);
  panel.appendChild(footer);

  root.appendChild(panel);

  let open = false;
  let busy = false;
  const sessionId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `s-${Date.now()}`;

  function setOpen(next: boolean) {
    open = next;
    panel.classList.toggle('is-open', open);
    launcher.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      input.focus();
    }
  }

  launcher.addEventListener('click', () => setOpen(!open));
  closeBtn.addEventListener('click', () => setOpen(false));

  composer.addEventListener('submit', async (event) => {
    event.preventDefault();
    const textContent = input.value.trim();
    if (!textContent || busy) return;
    input.value = '';
    addBubble(textContent, 'user');
    busy = true;
    send.disabled = true;
    input.disabled = true;
    const thinking = startThinking(messages, thinkingStatuses);
    try {
      const res = await fetch(`${base}/api/public/widgets/${widgetId}/messages`, {
        method: 'POST',
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: textContent, session_id: sessionId }),
      });
      thinking.stop();
      if (!res.ok) throw new Error(`message ${res.status}`);
      const data = (await res.json()) as MessageOut;
      addBubble(data.answer || (rtl ? 'تعذّر الرد.' : 'No reply.'), 'bot');
    } catch (err) {
      thinking.stop();
      console.error('[Geem Widget] message failed', err);
      addBubble(
        rtl ? 'حدث خطأ. حاول مرة أخرى.' : 'Something went wrong. Try again.',
        'bot',
      );
    } finally {
      busy = false;
      send.disabled = false;
      input.disabled = false;
      if (open) input.focus();
    }
  });
}

boot();
