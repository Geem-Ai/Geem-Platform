import { useState } from 'react';
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
} from '@/components/ui/sheet';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
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

/** Metronic store-inventory ProductDetails sheet — floating inset panel. */
const SHEET_PANEL =
  'gap-0 w-full sm:max-w-none sm:w-[min(100%-2.5rem,42rem)] lg:w-[48rem] inset-5 border start-auto h-auto rounded-lg p-0 [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5';

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
  const { currentMembership, currentWorkspace } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;

  const expertQuery = useExpert(open ? expertId : undefined);
  const expert = expertQuery.data;
  const knowledgeQuery = useExpertKnowledge(
    open && expert?.ownership === 'workspace' ? expertId : undefined,
  );
  const deleteMutation = useDeleteExpert();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const canEdit = expert ? canEditExpert(role, expert.ownership) : false;
  const canDelete = expert ? canDeleteExpert(role, expert.ownership) : false;
  const canManageKnowledge = expert
    ? canManageExpertKnowledge(role, expert.ownership)
    : false;
  const canAsk = expert ? canAskExpert(expert.status) : false;
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
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="end" className={SHEET_PANEL}>
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
