/** Locale-aware message timestamp for chat bubbles. */
export function formatMessageDateTime(
  iso: string,
  language: string,
): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const locale = language.toLowerCase().startsWith('ar') ? 'ar-SA' : 'en-GB';
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (sameDay) {
    return new Intl.DateTimeFormat(locale, {
      hour: 'numeric',
      minute: '2-digit',
    }).format(date);
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

/** Exact local timestamp for tooltips: `Y-m-d H:i:s`. */
export function formatMessageDateTimeExact(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const pad = (n: number) => String(n).padStart(2, '0');
  const y = date.getFullYear();
  const m = pad(date.getMonth() + 1);
  const d = pad(date.getDate());
  const h = pad(date.getHours());
  const i = pad(date.getMinutes());
  const s = pad(date.getSeconds());
  return `${y}-${m}-${d} ${h}:${i}:${s}`;
}
