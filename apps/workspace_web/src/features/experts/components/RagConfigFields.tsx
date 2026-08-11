import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { ExpertRagConfig } from '@/services/api/types';
import {
  clampRagValue,
  parseRagConfig,
  RAG_CONFIG_BOUNDS,
} from '../lib/rag-config';

interface RagConfigFieldsProps {
  value: ExpertRagConfig | null | undefined;
  onChange: (value: {
    top_k: number;
    rerank_top_n: number;
    similarity_threshold: number;
  }) => void;
  disabled?: boolean;
}

export function RagConfigFields({ value, onChange, disabled }: RagConfigFieldsProps) {
  const { t } = useTranslation();
  const parsed = parseRagConfig(value);

  function handleChange(
    key: 'top_k' | 'rerank_top_n' | 'similarity_threshold',
    raw: string,
  ) {
    const num = parseFloat(raw);
    if (isNaN(num)) return;
    const clamped = clampRagValue(key, num);
    onChange({ ...parsed, [key]: clamped });
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium">{t('experts.advancedSettings')}</h3>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label htmlFor="rag-top-k">{t('experts.topK')}</Label>
          <Input
            id="rag-top-k"
            type="number"
            value={parsed.top_k ?? ''}
            onChange={(e) => handleChange('top_k', e.target.value)}
            disabled={disabled}
            min={RAG_CONFIG_BOUNDS.top_k.min}
            max={RAG_CONFIG_BOUNDS.top_k.max}
          />
          <p className="text-xs text-muted-foreground">{t('experts.topKHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="rag-rerank">{t('experts.rerankTopN')}</Label>
          <Input
            id="rag-rerank"
            type="number"
            value={parsed.rerank_top_n ?? ''}
            onChange={(e) => handleChange('rerank_top_n', e.target.value)}
            disabled={disabled}
            min={RAG_CONFIG_BOUNDS.rerank_top_n.min}
            max={RAG_CONFIG_BOUNDS.rerank_top_n.max}
          />
          <p className="text-xs text-muted-foreground">{t('experts.rerankTopNHint')}</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="rag-threshold">{t('experts.similarityThreshold')}</Label>
          <Input
            id="rag-threshold"
            type="number"
            value={parsed.similarity_threshold ?? ''}
            onChange={(e) => handleChange('similarity_threshold', e.target.value)}
            disabled={disabled}
            min={RAG_CONFIG_BOUNDS.similarity_threshold.min}
            max={RAG_CONFIG_BOUNDS.similarity_threshold.max}
            step={RAG_CONFIG_BOUNDS.similarity_threshold.step}
          />
          <p className="text-xs text-muted-foreground">{t('experts.similarityThresholdHint')}</p>
        </div>
      </div>
    </div>
  );
}
