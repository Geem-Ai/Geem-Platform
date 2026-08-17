/**
 * Clean OCR/chunk citation snippets for display.
 * Strip markdown/HTML image placeholders that often appear in extracted PDFs.
 */
export function sanitizeCitationSnippet(raw: string | null | undefined): string {
  if (!raw) return '';

  let text = raw
    // Markdown images: ![alt](url) or ![](url)
    .replace(/!\[[^\]]*]\([^)]*\)/g, ' ')
    // HTML img tags (self-closing or with body)
    .replace(/<img\b[^>]*\/?>/gi, ' ')
    .replace(/<\/img>/gi, ' ');

  // Collapse whitespace (including newlines) into single spaces
  text = text.replace(/\s+/g, ' ').trim();

  return text;
}

/** Character length above which citation snippets offer expand/collapse. */
export const CITATION_SNIPPET_EXPAND_THRESHOLD = 180;
