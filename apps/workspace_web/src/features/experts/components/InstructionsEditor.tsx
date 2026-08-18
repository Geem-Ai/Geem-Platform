import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { GenerateInstructionsDialog } from './GenerateInstructionsDialog';

const MAX_CHARS = 32000;

interface InstructionsEditorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
  /** Soft context passed into the AI-assist dialog. */
  expertName?: string;
  expertDescription?: string;
  /** Hide the AI generate control (e.g. read-only views). Default: show. */
  allowGenerate?: boolean;
}

export function InstructionsEditor({
  value,
  onChange,
  disabled,
  id = 'instructions-editor',
  expertName,
  expertDescription,
  allowGenerate = true,
}: InstructionsEditorProps) {
  const { t } = useTranslation();
  const [generateOpen, setGenerateOpen] = useState(false);
  const remaining = MAX_CHARS - value.length;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Label htmlFor={id}>{t('experts.instructions')}</Label>
          {allowGenerate ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7 shrink-0 text-primary/80 hover:text-primary"
                  disabled={disabled}
                  onClick={() => setGenerateOpen(true)}
                  aria-label={t('experts.generateInstructions.open')}
                  data-testid="generate-instructions-button"
                >
                  <Sparkles className="ai-sparkle-pulse size-3.5" aria-hidden />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {t('experts.generateInstructions.open')}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
        <span className={`text-xs shrink-0 ${remaining < 500 ? 'text-destructive' : 'text-muted-foreground'}`}>
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

      {allowGenerate ? (
        <GenerateInstructionsDialog
          open={generateOpen}
          onOpenChange={setGenerateOpen}
          currentInstructions={value}
          expertName={expertName}
          expertDescription={expertDescription}
          onGenerated={onChange}
        />
      ) : null}
    </div>
  );
}
