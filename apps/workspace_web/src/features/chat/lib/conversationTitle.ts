/** Sidebar-friendly provisional title from the first user message (no LLM). */
export function provisionalConversationTitle(
  text: string,
  maxLength = 80,
): string {
  const cleaned = (text || '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return '';
  if (maxLength < 1 || cleaned.length <= maxLength) return cleaned;

  const truncated = cleaned.slice(0, maxLength);
  const boundary = truncated.lastIndexOf(' ');
  if (boundary >= Math.max(8, Math.floor(maxLength / 3))) {
    return `${truncated.slice(0, boundary).replace(/[.,;:!?،؛]+$/u, '')}…`;
  }
  return `${truncated.trimEnd()}…`;
}

/** Reject LLM junk titles that should not replace a provisional topic title. */
export function isUsableConversationTitle(title: string | null | undefined): boolean {
  const cleaned = (title || '').replace(/\s+/g, ' ').trim();
  if (cleaned.length < 3) return false;
  const lower = cleaned.toLocaleLowerCase();
  if (
    /^(title|عنوان|language|اللغة|topic|subject|موضوع)\s*[:：\-–—]?\s*$/iu.test(
      cleaned,
    )
  ) {
    return false;
  }
  const junk = new Set([
    'language',
    'title',
    'arabic',
    'english',
    'topic',
    'subject',
    'عنوان',
    'اللغة',
    'عربي',
    'العربية',
    'الإنجليزية',
    'موضوع',
  ]);
  if (junk.has(lower)) return false;
  return true;
}
