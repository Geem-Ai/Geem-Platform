/** User-facing Geem model id — never show provider/OpenRouter model names. */
export const PUBLIC_MODEL_ID = 'dalseen/geem-1.0';

export function publicModelId(_raw?: string | null): string {
  return PUBLIC_MODEL_ID;
}

export function publicModelOrNone(raw?: string | null): string | null {
  if (raw == null || raw === '') return null;
  return PUBLIC_MODEL_ID;
}
