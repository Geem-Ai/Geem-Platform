import { useTranslation } from 'react-i18next';
import type { Citation } from '@/services/api/types';

interface CitationListProps {
  citations: Citation[];
  /** Platform citations are metadata-only — never link to raw Document APIs. */
  isPlatform?: boolean;
}

export function CitationList({ citations, isPlatform = false }: CitationListProps) {
  const { t } = useTranslation();

  if (citations.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {t('chat.citations')}
        {isPlatform ? ` · ${t('experts.platformBadge')}` : ''}
      </p>
      <ol className="space-y-1.5 list-decimal list-inside">
        {citations.map((c, index) => (
          <li
            key={c.chunk_id || `${c.document_id}-${c.page}-${index}`}
            className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs marker:text-muted-foreground"
          >
            <div className="inline-flex flex-col gap-0.5 align-top w-[calc(100%-1.25rem)]">
              <div className="flex items-center gap-2">
                <span className="font-medium truncate">{c.document_title}</span>
                {c.page > 0 && (
                  <span className="text-muted-foreground shrink-0">
                    {t('chat.page', { page: c.page })}
                  </span>
                )}
              </div>
              {c.snippet && (
                <p className="text-muted-foreground line-clamp-3">{c.snippet}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
