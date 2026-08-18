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

function css(): string {
  return `
.geem-widget-root{all:initial;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.geem-widget-root *{box-sizing:border-box}
.geem-launcher{position:fixed;z-index:2147483000;width:56px;height:56px;border-radius:999px;border:none;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center}
.geem-panel{position:fixed;z-index:2147483000;width:min(380px,calc(100vw - 24px));height:min(560px,calc(100vh - 100px));border-radius:16px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 16px 48px rgba(0,0,0,.28);background:#fff;color:#111}
.geem-header{padding:14px 16px;display:flex;gap:10px;align-items:center}
.geem-header img{width:36px;height:36px;border-radius:8px;object-fit:cover;background:rgba(255,255,255,.15)}
.geem-header h1{margin:0;font-size:15px;font-weight:700;line-height:1.2}
.geem-header p{margin:2px 0 0;font-size:12px;opacity:.85}
.geem-messages{flex:1;overflow:auto;padding:14px;background:#f6f7f9;display:flex;flex-direction:column;gap:10px}
.geem-bubble{max-width:85%;padding:10px 12px;border-radius:12px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
.geem-bubble.bot{align-self:flex-start;background:#fff;border:1px solid #e6e8ec}
.geem-bubble.user{align-self:flex-end;color:#fff}
.geem-composer{display:flex;gap:8px;padding:10px;border-top:1px solid #e6e8ec;background:#fff}
.geem-composer input{flex:1;border:1px solid #d7dbe3;border-radius:10px;padding:10px 12px;font-size:14px;outline:none}
.geem-composer button{border:none;border-radius:10px;padding:0 14px;cursor:pointer;font-weight:600;color:#fff}
.geem-close{margin-inline-start:auto;background:transparent;border:none;color:inherit;cursor:pointer;font-size:18px;opacity:.85}
`;
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

  const style = document.createElement('style');
  style.textContent = css();
  document.head.appendChild(style);

  const root = document.createElement('div');
  root.className = 'geem-widget-root';
  root.setAttribute('dir', rtl ? 'rtl' : 'ltr');
  document.body.appendChild(root);

  const launcher = document.createElement('button');
  launcher.type = 'button';
  launcher.className = 'geem-launcher';
  launcher.style.background = primary;
  launcher.style.color = text;
  launcher.style.bottom = '20px';
  launcher.style[side] = '20px';
  launcher.setAttribute('aria-label', 'Open chat');
  launcher.innerHTML =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>';
  root.appendChild(launcher);

  const panel = document.createElement('div');
  panel.className = 'geem-panel';
  panel.hidden = true;
  panel.style.bottom = '88px';
  panel.style[side] = '20px';

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
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.textContent = '×';
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const messages = document.createElement('div');
  messages.className = 'geem-messages';
  panel.appendChild(messages);

  function addBubble(textContent: string, kind: 'bot' | 'user') {
    const el = document.createElement('div');
    el.className = `geem-bubble ${kind}`;
    if (kind === 'user') el.style.background = primary;
    el.textContent = textContent;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
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
  root.appendChild(panel);

  let open = false;
  let busy = false;
  const sessionId =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `s-${Date.now()}`;

  function setOpen(next: boolean) {
    open = next;
    panel.hidden = !open;
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
    try {
      const res = await fetch(`${base}/api/public/widgets/${widgetId}/messages`, {
        method: 'POST',
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: textContent, session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`message ${res.status}`);
      const data = (await res.json()) as MessageOut;
      addBubble(data.answer || (rtl ? 'تعذّر الرد.' : 'No reply.'), 'bot');
    } catch (err) {
      console.error('[Geem Widget] message failed', err);
      addBubble(
        rtl ? 'حدث خطأ. حاول مرة أخرى.' : 'Something went wrong. Try again.',
        'bot',
      );
    } finally {
      busy = false;
      send.disabled = false;
      input.focus();
    }
  });
}

boot();
