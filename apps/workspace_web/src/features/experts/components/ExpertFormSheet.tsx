import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { QuotaAlert } from '@/features/usage/components/QuotaAlert';
import { useUsageSummary } from '@/features/usage/hooks/useUsageQueries';
import { meterWarningLevel } from '@/features/usage/lib/quota';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  floatingSheetPanel,
} from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { InstructionsEditor } from './InstructionsEditor';
import { RagConfigFields } from './RagConfigFields';
import { ClientAgentToggle } from './ClientAgentToggle';
import { useAgentsAiUsage } from '@/features/apps/hooks/useAppsQueries';
import { useCreateExpert, useUpdateExpert } from '../hooks/useExpertMutations';
import { useExpert } from '../hooks/useExpert';
import {
  isClientAgentEnabled,
  parseRagConfig,
  serializeRagConfig,
} from '../lib/rag-config';

/** Metronic store-inventory ProductFormSheet layout — floating inset panel. */
const SHEET_PANEL = floatingSheetPanel(
  'sm:w-[min(100%-2.5rem,40rem)]',
  'lg:w-[44rem]',
);

export type ExpertFormSheetMode = 'create' | 'edit';

type ExpertFormSheetProps = {
  mode: ExpertFormSheetMode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  expertId?: string;
  onCreated?: (expertId: string) => void;
  onSaved?: (expertId: string) => void;
};

export function ExpertFormSheet({
  mode,
  open,
  onOpenChange,
  expertId,
  onCreated,
  onSaved,
}: ExpertFormSheetProps) {
  const { t } = useTranslation();
  const isCreate = mode === 'create';
  const expertQuery = useExpert(isCreate ? undefined : expertId);
  const createMutation = useCreateExpert();
  const updateMutation = useUpdateExpert(expertId ?? '');
  const usageQuery = useUsageSummary();
  const agentsAiUsageQuery = useAgentsAiUsage(open && !isCreate);
  const expertsMeter = usageQuery.data?.experts;
  const expertsExhausted =
    isCreate && expertsMeter != null && meterWarningLevel(expertsMeter) === 'exhausted';
  const [createQuotaCode, setCreateQuotaCode] = useState<'expert_limit_reached' | null>(
    null,
  );

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [ragConfig, setRagConfig] = useState(parseRagConfig(null));
  const [clientAgentEnabled, setClientAgentEnabled] = useState(false);

  const pending = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!open) return;
    if (isCreate) {
      setName('');
      setDescription('');
      setInstructions('');
      setRagConfig(parseRagConfig(null));
      setClientAgentEnabled(false);
      setCreateQuotaCode(null);
      return;
    }
    const expert = expertQuery.data;
    if (!expert) return;
    if (expert.ownership === 'platform') {
      onOpenChange(false);
      return;
    }
    setName(expert.name);
    setDescription(expert.description ?? '');
    setInstructions(expert.system_instructions ?? '');
    setRagConfig(parseRagConfig(expert.rag_config));
    setClientAgentEnabled(isClientAgentEnabled(expert.rag_config));
  }, [open, isCreate, expertQuery.data, onOpenChange]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    if (isCreate) {
      createMutation.mutate(
        {
          name: name.trim(),
          description: description.trim() || null,
          system_instructions: instructions.trim() || null,
        },
        {
          onSuccess: (expert) => {
            toast.success(t('experts.created'));
            onCreated?.(expert.id);
          },
          onError: (err: unknown) => {
            if (err instanceof ApiError) {
              if (err.code === 'expert_limit_reached') {
                setCreateQuotaCode('expert_limit_reached');
              }
              toast.error(t(errorMessageKey(err.code)));
            } else {
              toast.error(t('errors.generic'));
            }
          },
        },
      );
      return;
    }

    if (!expertId) return;
    updateMutation.mutate(
      {
        name: name.trim(),
        description: description.trim() || null,
        system_instructions: instructions.trim() || null,
        rag_config: serializeRagConfig(ragConfig, clientAgentEnabled),
      },
      {
        onSuccess: () => {
          toast.success(t('experts.saved'));
          onSaved?.(expertId);
        },
        onError: (err: unknown) => {
          if (err instanceof ApiError) {
            toast.error(t(errorMessageKey(err.code)));
          } else {
            toast.error(t('errors.generic'));
          }
        },
      },
    );
  }

  const loadingEdit = !isCreate && expertQuery.isLoading;
  const editError = !isCreate && (expertQuery.isError || !expertQuery.data);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="end" className={SHEET_PANEL}>
        <SheetHeader className="border-b py-3.5 px-5 border-border text-start">
          <SheetTitle className="font-medium">
            {isCreate ? t('experts.createTitle') : t('experts.editTitle')}
          </SheetTitle>
        </SheetHeader>

        <form className="flex flex-col grow min-h-0" onSubmit={handleSubmit}>
          <SheetBody className="p-0 grow min-h-0">
            {loadingEdit && (
              <p className="p-5 text-sm text-muted-foreground">{t('shell.loading')}</p>
            )}
            {editError && (
              <p className="p-5 text-sm text-destructive">{t('errors.expertNotFound')}</p>
            )}
            {!loadingEdit && !editError && (
              <ScrollArea className="h-[calc(100dvh-12rem)]">
                <div className="space-y-5 p-5">
                  {isCreate && (expertsExhausted || createQuotaCode) ? (
                    <QuotaAlert
                      code="expert_limit_reached"
                      level="exhausted"
                    />
                  ) : null}
                  <Card className="rounded-md">
                    <CardHeader className="min-h-[38px] bg-accent/50">
                      <CardTitle className="text-sm">{t('experts.basicInfo')}</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4 space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="expert-sheet-name" className="text-xs">
                          {t('experts.name')}
                        </Label>
                        <Input
                          id="expert-sheet-name"
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                          placeholder={t('experts.namePlaceholder')}
                          maxLength={200}
                          required
                          disabled={pending}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="expert-sheet-description" className="text-xs">
                          {t('experts.descriptionField')}
                        </Label>
                        <Textarea
                          id="expert-sheet-description"
                          value={description}
                          onChange={(e) => setDescription(e.target.value)}
                          placeholder={t('experts.descriptionPlaceholder')}
                          maxLength={2000}
                          disabled={pending}
                        />
                      </div>
                    </CardContent>
                  </Card>

                  <Card className="rounded-md">
                    <CardHeader className="min-h-[38px] bg-accent/50">
                      <CardTitle className="text-sm">{t('experts.instructions')}</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <InstructionsEditor
                        value={instructions}
                        onChange={setInstructions}
                        disabled={pending}
                        id={isCreate ? 'create-instructions' : 'edit-instructions'}
                        expertName={name}
                        expertDescription={description}
                      />
                    </CardContent>
                  </Card>

                  {!isCreate && (
                    <Card className="rounded-md">
                      <CardHeader className="min-h-[38px] bg-accent/50">
                        <CardTitle className="text-sm">{t('experts.advancedSettings')}</CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4">
                        <div className="space-y-5">
                          <RagConfigFields
                            value={ragConfig}
                            onChange={setRagConfig}
                            disabled={pending}
                          />
                          <div className="border-t border-border pt-5">
                            <ClientAgentToggle
                              checked={clientAgentEnabled}
                              onCheckedChange={setClientAgentEnabled}
                              usage={agentsAiUsageQuery.data}
                              accessLoading={agentsAiUsageQuery.isLoading}
                              accessError={agentsAiUsageQuery.isError}
                              pending={pending}
                            />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              </ScrollArea>
            )}
          </SheetBody>

          <SheetFooter className="flex-row border-t justify-end items-center p-5 border-border gap-2 sm:space-x-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || pending || loadingEdit || Boolean(editError) || expertsExhausted || Boolean(createQuotaCode)}>
              {pending
                ? t('experts.saving')
                : isCreate
                  ? t('experts.create')
                  : t('common.save')}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
