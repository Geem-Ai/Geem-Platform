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
  onChange?: (value: ExpertRagConfig) => void;
  disabled?: boolean;
}

export function RagConfigFields({ value, onChange, disabled }: RagConfigFieldsProps) {
  const { t } = useTranslation();
  const parsed = parseRagConfig(value);

  function handleChange(
    key: 'top_k' | 'rerank_top_n' | 'similarity_threshold',
    raw: string,
  ) {
    if (!onChange) return;
    const num = parseFloat(raw);
    if (Number.isNaN(num)) return;
    onChange({ ...parsed, [key]: clampRagValue(key, num) });
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {(['top_k', 'rerank_top_n', 'similarity_threshold'] as const).map((key) => (
        <div key={key} className="space-y-1.5">
          <Label htmlFor={`rag-${key}`}>{t(`experts.rag.${key}`)}</Label>
          <Input
            id={`rag-${key}`}
            type="number"
            min={RAG_CONFIG_BOUNDS[key].min}
            max={RAG_CONFIG_BOUNDS[key].max}
            step={key === 'similarity_threshold' ? 0.01 : 1}
            value={parsed[key]}
            disabled={disabled || !onChange}
            onChange={(e) => handleChange(key, e.target.value)}
          />
        </div>
      ))}
    </div>
  );
}
