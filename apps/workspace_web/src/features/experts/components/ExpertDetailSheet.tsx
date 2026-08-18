import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SquarePen } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
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
import {
  isGooglePickerEventTarget,
  isGooglePickerOpen,
  subscribeGooglePickerOpen,
} from '@/features/apps/google-drive/picker';
import { usePermissions } from '@/features/authz/usePermissions';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  canAskExpert,
  canDeleteExpert,
  canEditExpert,
  canManageExpertKnowledge,
} from '../lib/capabilities';
import { localizeExpertDisplay } from '../lib/localize';
import { useExpert } from '../hooks/useExpert';
import { useExpertKnowledge } from '../hooks/useExpertKnowledge';
import { useDeleteExpert } from '../hooks/useExpertMutations';
import { DeleteExpertDialog } from './DeleteExpertDialog';
import { ExpertAvatar } from './ExpertAvatar';
import { ExpertStatusBadge } from './ExpertStatusBadge';
import { ExpertApiIdField } from './ExpertApiIdField';
import { KnowledgeSourcesPanel } from './KnowledgeSourcesPanel';
import { RagConfigFields } from './RagConfigFields';

const SHEET_PANEL = floatingSheetPanel(
  'sm:w-[min(100%-2.5rem,42rem)]',
  'lg:w-[48rem]',
);

type ExpertDetailSheetProps = {
  expertId: string | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit?: (expertId: string) => void;
  onDeleted?: () => void;
};

export function ExpertDetailSheet({
  expertId,
  open,
  onOpenChange,
  onEdit,
  onDeleted,
}: ExpertDetailSheetProps) {
  const { t } = useTranslation();
  const { can } = usePermissions();

  const expertQuery = useExpert(open ? expertId : undefined);
  const expert = expertQuery.data;
  const knowledgeQuery = useExpertKnowledge(
    open && expert?.ownership === 'workspace' ? expertId : undefined,
  );
  const deleteMutation = useDeleteExpert();
  const [deleteOpen, setDeleteOpen] = useState(false);
  /** Google Picker sits outside Sheet DOM; keep Expert sheet open while it is. */
  const [googlePickerOpen, setGooglePickerOpen] = useState(isGooglePickerOpen);

  useEffect(() => {
    return subscribeGooglePickerOpen(() => {
      setGooglePickerOpen(isGooglePickerOpen());
    });
  }, []);

  function blockDismissForGooglePicker(event: Event) {
    if (
      googlePickerOpen ||
      isGooglePickerOpen() ||
      isGooglePickerEventTarget(event.target)
    ) {
      event.preventDefault();
    }
  }

  const canEdit = expert ? canEditExpert(can, expert.ownership) : false;
  const canDelete = expert ? canDeleteExpert(can, expert.ownership) : false;
  const canManageKnowledge = expert
    ? canManageExpertKnowledge(can, expert.ownership)
    : false;
  const canAsk = expert ? canAskExpert(can, expert.status) : false;
  const display = expert ? localizeExpertDisplay(expert, t) : null;

  function handleDelete() {
    if (!expert) return;
    deleteMutation.mutate(expert.id, {
      onSuccess: () => {
        toast.success(t('experts.deleted'));
        setDeleteOpen(false);
        onOpenChange(false);
        onDeleted?.();
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('errors.generic'));
        }
        setDeleteOpen(false);
      },
    });
  }

  return (
    <Sheet
      open={open}
      // Modal mode sets pointer-events:none on the rest of the document, which
      // makes Google Picker (ported outside Sheet) unclickable.
      modal={!googlePickerOpen}
      onOpenChange={(next) => {
        if (!next && (googlePickerOpen || isGooglePickerOpen())) return;
        onOpenChange(next);
      }}
    >
      <SheetContent
        side="end"
        className={SHEET_PANEL}
        // Drop the dimmed overlay while Picker is up so it cannot steal hits.
        overlay={!googlePickerOpen}
        onPointerDownOutside={blockDismissForGooglePicker}
        onInteractOutside={blockDismissForGooglePicker}
        onFocusOutside={blockDismissForGooglePicker}
        onEscapeKeyDown={blockDismissForGooglePicker}
      >
        <SheetHeader className="border-b py-3.5 px-5 border-border text-start">
          <div className="flex items-start justify-between gap-3 pe-8">
            <div className="flex items-center gap-3 min-w-0">
              <ExpertAvatar
                name={display?.name ?? t('experts.title')}
                iconUrl={expert?.icon_url}
                ownership={expert?.ownership ?? 'workspace'}
                size="md"
              />
              <div className="min-w-0 space-y-1">
                <SheetTitle className="font-medium truncate">
                  {display?.name ?? t('experts.title')}
                </SheetTitle>
                {display?.description && (
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {display.description}
                  </p>
                )}
              </div>
            </div>
            {expert && <ExpertStatusBadge status={expert.status} />}
          </div>
        </SheetHeader>

        <SheetBody className="p-0 grow min-h-0">
          {expertQuery.isLoading && (
            <p className="p-5 text-sm text-muted-foreground">{t('shell.loading')}</p>
          )}
          {(expertQuery.isError || (!expertQuery.isLoading && !expert)) && (
            <p className="p-5 text-sm text-destructive">{t('errors.expertNotFound')}</p>
          )}
          {expert && (
            <ScrollArea className="h-[calc(100dvh-12rem)]">
              <div className="space-y-5 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" appearance="light" size="sm">
                    {expert.ownership === 'platform'
                      ? t('experts.platformBadge')
                      : t(`experts.type.${expert.ownership}`)}
                  </Badge>
                  {expert.ownership === 'workspace' && (
                    <span className="text-xs text-muted-foreground">
                      {t('experts.knowledgeCount', {
                        count: expert.knowledge_document_count,
                      })}
                    </span>
                  )}
                </div>

                <Card className="rounded-md">
                  <CardContent className="pt-4">
                    <ExpertApiIdField expertId={expert.id} />
                  </CardContent>
                </Card>

                {expert.ownership === 'workspace' && (
                  <Card className="rounded-md">
                    <CardContent className="pt-4">
                      <KnowledgeSourcesPanel
                        expertId={expert.id}
                        items={knowledgeQuery.data ?? []}
                        canManage={canManageKnowledge}
                        isLoading={knowledgeQuery.isLoading}
                        isError={knowledgeQuery.isError}
                      />
                    </CardContent>
                  </Card>
                )}

                {expert.ownership === 'platform' && (
                  <Card className="rounded-md">
                    <CardContent className="pt-4">
                      <p className="text-sm text-muted-foreground">
                        {t('experts.platformManaged')}
                      </p>
                    </CardContent>
                  </Card>
                )}

                {expert.ownership === 'workspace' && (
                  <Card className="rounded-md">
                    <CardHeader className="min-h-[38px] bg-accent/50">
                      <CardTitle className="text-sm">{t('experts.instructions')}</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      {expert.system_instructions ? (
                        <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">
                          {expert.system_instructions}
                        </pre>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          {t('experts.knowledgeEmptyHint')}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )}

                {expert.ownership === 'workspace' && expert.rag_config && (
                  <Card className="rounded-md">
                    <CardHeader className="min-h-[38px] bg-accent/50">
                      <CardTitle className="text-sm">
                        {t('experts.advancedSettings')}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <RagConfigFields value={expert.rag_config} readOnly />
                    </CardContent>
                  </Card>
                )}

                {canDelete && (
                  <Card className="rounded-md border-destructive/40">
                    <CardHeader className="min-h-[38px]">
                      <CardTitle className="text-sm text-destructive">
                        {t('experts.dangerZone')}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => setDeleteOpen(true)}
                      >
                        {t('experts.deleteTitle')}
                      </Button>
                    </CardContent>
                  </Card>
                )}
              </div>
            </ScrollArea>
          )}
        </SheetBody>

        <SheetFooter className="flex-row border-t justify-between items-center p-5 border-border gap-2 sm:space-x-0">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('shell.close')}
          </Button>
          <div className="flex items-center gap-2">
            {canEdit && expert && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onEdit?.(expert.id)}
              >
                <SquarePen className="size-3.5" />
                {t('experts.edit')}
              </Button>
            )}
            {canAsk && expert && (
              <Button asChild size="sm">
                <Link to={`/chat?expert=${expert.id}`}>{t('experts.ask')}</Link>
              </Button>
            )}
          </div>
        </SheetFooter>
      </SheetContent>

      {canDelete && expert && (
        <DeleteExpertDialog
          expert={expert}
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          onConfirm={handleDelete}
          isPending={deleteMutation.isPending}
        />
      )}
    </Sheet>
  );
}
