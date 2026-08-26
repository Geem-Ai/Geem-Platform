import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Wrench } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { Citation } from '@/services/api/types';
import {
  CITATION_SNIPPET_EXPAND_THRESHOLD,
  sanitizeCitationSnippet,
} from '../lib/sanitizeCitationSnippet';

interface CitationListProps {
  citations: Citation[];
  /** Platform citations are metadata-only — never link to raw Document APIs. */
  isPlatform?: boolean;
}

function CitationCard({
  citation,
  index,
}: {
  citation: Citation;
  index: number;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (citation.kind === 'tool') {
    const connection = citation.connection_display_name || citation.connection_name;
    return (
      <li className="rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-xs" data-testid="tool-citation-item">
        <div className="flex gap-2.5">
          <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-background border border-border text-[0.6875rem] font-semibold tabular-nums text-muted-foreground" aria-hidden>{index + 1}</span>
          <div className="min-w-0 flex-1 flex items-start gap-2">
            <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0"><p className="font-medium text-foreground truncate" dir="auto">{citation.tool_title || citation.tool_name}</p>{connection ? <p className="text-muted-foreground truncate" dir="auto">{connection}</p> : null}</div>
          </div>
        </div>
      </li>
    );
  }
  const snippet = sanitizeCitationSnippet(citation.snippet);
  const canExpand = snippet.length > CITATION_SNIPPET_EXPAND_THRESHOLD;

  return (
    <li
      className="rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-xs"
      data-testid="citation-item"
    >
      <div className="flex gap-2.5">
        <span
          className="flex size-5 shrink-0 items-center justify-center rounded-md bg-background border border-border text-[0.6875rem] font-semibold tabular-nums text-muted-foreground"
          aria-hidden
        >
          {index + 1}
        </span>

        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-start gap-2">
            <FileText
              className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
              aria-hidden
            />
            <div className="min-w-0 flex-1 flex flex-wrap items-center gap-x-2 gap-y-1">
              <span
                className="font-medium text-foreground truncate max-w-full"
                dir="auto"
                title={citation.document_title}
              >
                {citation.document_title}
              </span>
              {citation.page > 0 && (
                <Badge
                  variant="secondary"
                  appearance="outline"
                  size="xs"
                  className="shrink-0 font-normal text-muted-foreground"
                >
                  {t('chat.page', { page: citation.page })}
                </Badge>
              )}
            </div>
          </div>

          {snippet ? (
            <div className="space-y-1">
              <p
                className={cn(
                  'text-muted-foreground leading-relaxed',
                  !expanded && 'line-clamp-3',
                )}
                dir="auto"
                data-testid="citation-snippet"
              >
                {snippet}
              </p>
              {canExpand && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 px-1.5 -ms-1.5 text-[0.6875rem] text-muted-foreground hover:text-foreground"
                  onClick={() => setExpanded((v) => !v)}
                  aria-expanded={expanded}
                >
                  {expanded ? t('chat.showLess') : t('chat.showMore')}
                </Button>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function CitationList({ citations, isPlatform = false }: CitationListProps) {
  const { t } = useTranslation();

  if (citations.length === 0) return null;

  return (
    <div className="mt-3 space-y-2" data-testid="citation-list">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {t('chat.citations')}
        {isPlatform ? ` · ${t('experts.platformBadge')}` : ''}
      </p>
      <ol className="space-y-2 list-none p-0 m-0">
        {citations.map((c, index) => (
          <CitationCard
            key={c.kind === 'tool'
              ? c.tool_call_id || `${c.connection_name}-${c.tool_name}-${index}`
              : c.chunk_id || `${c.document_id}-${c.page}-${index}`}
            citation={c}
            index={index}
          />
        ))}
      </ol>
    </div>
  );
}
