import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  generateExpertInstructions,
  type GenerateExpertInstructionsInput,
} from '@/services/api/experts';

const MAX_INSTRUCTIONS = 32000;

export type GenerateInstructionsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current instructions in the editor — used for overwrite warning. */
  currentInstructions: string;
  /** Soft context from the Expert form (name / description). */
  expertName?: string;
  expertDescription?: string;
  onGenerated: (instructions: string) => void;
};

export function GenerateInstructionsDialog({
  open,
  onOpenChange,
  currentInstructions,
  expertName = '',
  expertDescription = '',
  onGenerated,
}: GenerateInstructionsDialogProps) {
  const { t } = useTranslation();
  const [brief, setBrief] = useState('');
  const [persona, setPersona] = useState('');
  const [audience, setAudience] = useState('');
  const [tone, setTone] = useState('');
  const [constraints, setConstraints] = useState('');
  const [pending, setPending] = useState(false);

  const hasExisting = currentInstructions.trim().length > 0;

  useEffect(() => {
    if (!open) return;
    setBrief('');
    setPersona('');
    setAudience('');
    setTone('');
    setConstraints('');
    setPending(false);
  }, [open]);

  async function handleSubmit(e: FormEvent) {
    // Dialog content is portaled in the DOM, but React still bubbles submit
    // through the component tree — stop that so the parent Expert form does not save.
    e.preventDefault();
    e.stopPropagation();
    const trimmedBrief = brief.trim();
    if (!trimmedBrief || pending) return;

    const input: GenerateExpertInstructionsInput = {
      brief: trimmedBrief,
      persona: persona.trim() || null,
      audience: audience.trim() || null,
      tone: tone.trim() || null,
      constraints: constraints.trim() || null,
      name: expertName.trim() || null,
      description: expertDescription.trim() || null,
    };

    setPending(true);
    try {
      const result = await generateExpertInstructions(input);
      const next = result.system_instructions.slice(0, MAX_INSTRUCTIONS);
      onGenerated(next);
      toast.success(t('experts.generateInstructions.success'));
      onOpenChange(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('errors.generic'));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!pending) onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-lg" data-testid="generate-instructions-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" aria-hidden />
            {t('experts.generateInstructions.title')}
          </DialogTitle>
        </DialogHeader>

        <form className="space-y-4" onSubmit={handleSubmit}>
          {(expertName.trim() || expertDescription.trim()) && (
            <p className="text-xs text-muted-foreground rounded-md border border-border/70 bg-muted/40 px-3 py-2">
              {expertName.trim() ? (
                <span className="font-medium text-foreground">{expertName.trim()}</span>
              ) : null}
              {expertName.trim() && expertDescription.trim() ? ' — ' : null}
              {expertDescription.trim() || null}
            </p>
          )}

          {hasExisting ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              {t('experts.generateInstructions.overwriteWarning')}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="gen-instructions-brief">
              {t('experts.generateInstructions.brief')}
            </Label>
            <Textarea
              id="gen-instructions-brief"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder={t('experts.generateInstructions.briefPlaceholder')}
              maxLength={4000}
              required
              disabled={pending}
              className="min-h-[96px]"
              data-testid="gen-instructions-brief"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="gen-instructions-persona">
                {t('experts.generateInstructions.persona')}
              </Label>
              <Input
                id="gen-instructions-persona"
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                placeholder={t('experts.generateInstructions.personaPlaceholder')}
                maxLength={2000}
                disabled={pending}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="gen-instructions-audience">
                {t('experts.generateInstructions.audience')}
              </Label>
              <Input
                id="gen-instructions-audience"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder={t('experts.generateInstructions.audiencePlaceholder')}
                maxLength={2000}
                disabled={pending}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="gen-instructions-tone">
              {t('experts.generateInstructions.tone')}
            </Label>
            <Input
              id="gen-instructions-tone"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              placeholder={t('experts.generateInstructions.tonePlaceholder')}
              maxLength={2000}
              disabled={pending}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="gen-instructions-constraints">
              {t('experts.generateInstructions.constraints')}
            </Label>
            <Textarea
              id="gen-instructions-constraints"
              value={constraints}
              onChange={(e) => setConstraints(e.target.value)}
              placeholder={t('experts.generateInstructions.constraintsPlaceholder')}
              maxLength={2000}
              disabled={pending}
              className="min-h-[72px]"
            />
          </div>

          <p className="text-xs text-muted-foreground">
            {t('experts.generateInstructions.billingHint')}
          </p>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={pending || !brief.trim()}
              data-testid="gen-instructions-submit"
            >
              <Sparkles className="size-3.5" aria-hidden />
              {pending
                ? t('experts.generateInstructions.generating')
                : t('experts.generateInstructions.generate')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
