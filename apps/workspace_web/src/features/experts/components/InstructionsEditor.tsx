import { useTranslation } from 'react-i18next';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

const MAX_CHARS = 32000;

interface InstructionsEditorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
}

export function InstructionsEditor({
  value,
  onChange,
  disabled,
  id = 'instructions-editor',
}: InstructionsEditorProps) {
  const { t } = useTranslation();
  const remaining = MAX_CHARS - value.length;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{t('experts.instructions')}</Label>
        <span className={`text-xs ${remaining < 500 ? 'text-destructive' : 'text-muted-foreground'}`}>
          {remaining.toLocaleString()} / {MAX_CHARS.toLocaleString()}
        </span>
      </div>
      <Textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        maxLength={MAX_CHARS}
        placeholder={t('experts.instructionsPlaceholder')}
        className="min-h-[160px] font-mono text-xs"
      />
      <p className="text-xs text-muted-foreground">{t('experts.instructionsHint')}</p>
    </div>
  );
}
