import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { ExpertRagConfig } from '@/services/api/types';
import {
  clampRagValue,
  parseRagConfig,
  RAG_CONFIG_BOUNDS,
} from '../lib/rag-config';
import { FieldInfoTooltip } from './FieldInfoTooltip';

const SETTINGS = [
  {
    key: 'top_k',
    id: 'rag-top-k',
    labelKey: 'experts.topK',
    hintKey: 'experts.topKHint',
    bounds: RAG_CONFIG_BOUNDS.top_k,
  },
  {
    key: 'rerank_top_n',
    id: 'rag-rerank',
    labelKey: 'experts.rerankTopN',
    hintKey: 'experts.rerankTopNHint',
    bounds: RAG_CONFIG_BOUNDS.rerank_top_n,
  },
  {
    key: 'similarity_threshold',
    id: 'rag-threshold',
    labelKey: 'experts.similarityThreshold',
    hintKey: 'experts.similarityThresholdHint',
    bounds: RAG_CONFIG_BOUNDS.similarity_threshold,
  },
] as const;

interface RagConfigFieldsProps {
  value: ExpertRagConfig | null | undefined;
  onChange?: (value: {
    top_k: number;
    rerank_top_n: number;
    similarity_threshold: number;
  }) => void;
  disabled?: boolean;
  readOnly?: boolean;
}

export function RagConfigFields({
  value,
  onChange,
  disabled,
  readOnly,
}: RagConfigFieldsProps) {
  const { t } = useTranslation();
  const parsed = parseRagConfig(value);

  function handleChange(
    key: 'top_k' | 'rerank_top_n' | 'similarity_threshold',
    raw: string,
  ) {
    if (!onChange) return;
    const num = parseFloat(raw);
    if (isNaN(num)) return;
    onChange({ ...parsed, [key]: clampRagValue(key, num) });
  }

  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed text-muted-foreground">
        {t('experts.advancedSettingsHint')}
      </p>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {SETTINGS.map((setting) => {
          const label = t(setting.labelKey);
          const fieldValue = parsed[setting.key];

          return (
            <div
              key={setting.key}
              className="rounded-lg border border-border bg-muted/30 p-3 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                {readOnly ? (
                  <span className="text-xs font-medium text-muted-foreground">{label}</span>
                ) : (
                  <Label htmlFor={setting.id} className="text-xs">
                    {label}
                  </Label>
                )}
                <FieldInfoTooltip label={label} content={t(setting.hintKey)} />
              </div>

              {readOnly ? (
                <p className="text-xl font-semibold tabular-nums tracking-tight text-foreground leading-none">
                  {fieldValue}
                </p>
              ) : (
                <Input
                  id={setting.id}
                  type="number"
                  value={fieldValue ?? ''}
                  onChange={(e) => handleChange(setting.key, e.target.value)}
                  disabled={disabled}
                  min={setting.bounds.min}
                  max={setting.bounds.max}
                  step={'step' in setting.bounds ? setting.bounds.step : undefined}
                  className="tabular-nums"
                />
              )}

              <p className="text-[11px] text-muted-foreground">
                {t('experts.ragRange', {
                  min: setting.bounds.min,
                  max: setting.bounds.max,
                })}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
