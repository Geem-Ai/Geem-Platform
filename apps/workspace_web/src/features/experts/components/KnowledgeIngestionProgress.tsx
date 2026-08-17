import { useTranslation } from 'react-i18next';
import { Progress } from '@/components/ui/progress';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import {
  ingestionProgressDetail,
  ingestionStageLabelKey,
  isProcessingDocStatus,
} from '../lib/status';

type KnowledgeIngestionProgressProps = {
  item: Pick<
    ExpertKnowledgeItem,
    'status' | 'page_count' | 'processed_pages' | 'progress' | 'current_stage' | 'mime_type'
  >;
  className?: string;
};

export function KnowledgeIngestionProgress({
  item,
  className,
}: KnowledgeIngestionProgressProps) {
  const { t } = useTranslation();

  if (!isProcessingDocStatus(item.status)) {
    return null;
  }

  const pageCount = Math.max(0, item.page_count ?? 0);
  const processed = Math.max(0, item.processed_pages ?? 0);
  const percent = Math.round(Math.max(0, Math.min(1, item.progress ?? 0)) * 100);
  const stageKey = ingestionStageLabelKey(item.current_stage);
  const isPdf =
    (item.mime_type ?? '').includes('pdf') || pageCount > 1;

  const detailSpec = ingestionProgressDetail({
    isPdf,
    pageCount,
    processed,
    currentStage: item.current_stage,
  });
  const detail =
    detailSpec.kind === 'waitingPage'
      ? t('experts.progressWaitingPage', {
          page: detailSpec.page,
          total: detailSpec.total,
        })
      : detailSpec.kind === 'pagesDone'
        ? t('experts.progressPagesDone', {
            processed: detailSpec.processed,
            total: detailSpec.total,
          })
        : t('experts.progressWorking');

  return (
    <div className={className}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <p className="text-[11px] text-muted-foreground truncate">
          {stageKey ? `${t(stageKey)} · ${detail}` : detail}
        </p>
        <span className="text-[11px] tabular-nums text-muted-foreground shrink-0">
          {percent}%
        </span>
      </div>
      <Progress value={percent} label={detail} />
    </div>
  );
}
