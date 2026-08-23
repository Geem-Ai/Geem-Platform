import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { ArrowLeft, Bot, Globe2, RefreshCw, ShieldCheck, Sparkles, Trash2, Upload } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { ExpertStatusBadge, ExpertVisibilityBadge } from '@/components/shared/StatusBadges';
import { RagConfigFields } from '@/features/experts/components/RagConfigFields';
import {
  acceptedFileTypes,
  validateExpertFile,
} from '@/features/experts/lib/file-validation';
import { parseRagConfig, serializeRagConfig } from '@/features/experts/lib/rag-config';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatAdminDate } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  deletePlatformExpert,
  disablePlatformExpertAllWorkspaces,
  enablePlatformExpertAllWorkspaces,
  fetchPlatformExpert,
  fetchPlatformExpertGrants,
  fetchPlatformExpertKnowledge,
  fetchPlatformWorkspaces,
  grantPlatformExpertWorkspace,
  platformQueryKeys,
  publishPlatformExpert,
  removePlatformExpertKnowledge,
  reprocessPlatformExpertKnowledge,
  revokePlatformExpertWorkspace,
  unpublishPlatformExpert,
  updatePlatformExpert,
  uploadPlatformExpertKnowledge,
} from '@/services/api/platform';

const PICKER_PAGE_SIZE = 10;
const GRANTS_PAGE_SIZE = 10;

export function ExpertDetailPage() {
  const { expertId = '' } = useParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [publishOpen, setPublishOpen] = useState(false);
  const [unpublishOpen, setUnpublishOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pickerSearch, setPickerSearch] = useState('');
  const [pickerOffset, setPickerOffset] = useState(0);
  const [grantsOffset, setGrantsOffset] = useState(0);
  const [removeDoc, setRemoveDoc] = useState<{ id: string; name: string } | null>(null);

  const expertQuery = useQuery({
    queryKey: platformQueryKeys.expert(expertId),
    queryFn: () => fetchPlatformExpert(expertId),
    enabled: Boolean(expertId),
  });

  const knowledgeQuery = useQuery({
    queryKey: platformQueryKeys.expertKnowledge(expertId),
    queryFn: () => fetchPlatformExpertKnowledge(expertId),
    enabled: Boolean(expertId) && expertQuery.data?.knowledge_mode === 'rag',
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const pending = items.some((item) =>
        ['queued', 'processing', 'pending'].includes(item.status),
      );
      return pending ? 4000 : false;
    },
  });

  const grantsQuery = useQuery({
    queryKey: platformQueryKeys.expertGrants(expertId, {
      limit: GRANTS_PAGE_SIZE,
      offset: grantsOffset,
    }),
    queryFn: () =>
      fetchPlatformExpertGrants(expertId, { limit: GRANTS_PAGE_SIZE, offset: grantsOffset }),
    enabled: Boolean(expertId),
  });

  const workspacePickerQuery = useQuery({
    queryKey: platformQueryKeys.workspaces({
      search: pickerSearch.trim() || undefined,
      kind: 'tenant',
      limit: PICKER_PAGE_SIZE,
      offset: pickerOffset,
    }),
    queryFn: () =>
      fetchPlatformWorkspaces({
        search: pickerSearch.trim() || undefined,
        kind: 'tenant',
        limit: PICKER_PAGE_SIZE,
        offset: pickerOffset,
      }),
    enabled: Boolean(expertId) && expertQuery.data?.availability_mode !== 'all_workspaces',
  });

  const expert = expertQuery.data;
  const isProtected = expert?.is_protected ?? false;
  const isRag = expert?.knowledge_mode === 'rag';
  const isPublished = expert?.visibility === 'platform_published';

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [ragConfig, setRagConfig] = useState(serializeRagConfig(parseRagConfig(null)));

  useEffect(() => {
    if (!expert) return;
    setName(expert.name);
    setDescription(expert.description ?? '');
    setInstructions(expert.system_instructions ?? '');
    setRagConfig(serializeRagConfig(parseRagConfig(expert.rag_config)));
  }, [expert]);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: platformQueryKeys.expert(expertId) }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'experts'] }),
      queryClient.invalidateQueries({ queryKey: platformQueryKeys.expertKnowledge(expertId) }),
      queryClient.invalidateQueries({
        queryKey: platformQueryKeys.expertGrants(expertId),
      }),
    ]);
  };

  const saveMutation = useMutation({
    mutationFn: () =>
      updatePlatformExpert(expertId, {
        name: name.trim(),
        description: description.trim() || null,
        system_instructions: instructions.trim() || null,
        rag_config: isRag ? ragConfig : undefined,
      }),
    onSuccess: async () => {
      toast.success(t('experts.saveSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const publishMutation = useMutation({
    mutationFn: () => publishPlatformExpert(expertId),
    onSuccess: async () => {
      toast.success(t('experts.publishSuccess'));
      setPublishOpen(false);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const unpublishMutation = useMutation({
    mutationFn: () => unpublishPlatformExpert(expertId),
    onSuccess: async () => {
      toast.success(t('experts.unpublishSuccess'));
      setUnpublishOpen(false);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deletePlatformExpert(expertId),
    onSuccess: async () => {
      toast.success(t('experts.deleteSuccess'));
      setDeleteOpen(false);
      await queryClient.invalidateQueries({ queryKey: ['platform', 'experts'] });
      navigate('/experts');
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const allWsMutation = useMutation({
    mutationFn: (enable: boolean) =>
      enable
        ? enablePlatformExpertAllWorkspaces(expertId)
        : disablePlatformExpertAllWorkspaces(expertId),
    onSuccess: async () => {
      toast.success(t('experts.accessUpdated'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const grantMutation = useMutation({
    mutationFn: (workspaceId: string) => grantPlatformExpertWorkspace(expertId, workspaceId),
    onSuccess: async () => {
      toast.success(t('experts.grantSuccess'));
      setPickerSearch('');
      setPickerOffset(0);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const revokeMutation = useMutation({
    mutationFn: (workspaceId: string) => revokePlatformExpertWorkspace(expertId, workspaceId),
    onSuccess: async () => {
      toast.success(t('experts.revokeSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadPlatformExpertKnowledge(expertId, file),
    onSuccess: async () => {
      toast.success(t('experts.uploadSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const reprocessMutation = useMutation({
    mutationFn: (documentId: string) => reprocessPlatformExpertKnowledge(expertId, documentId),
    onSuccess: async () => {
      toast.success(t('experts.reprocessSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const removeMutation = useMutation({
    mutationFn: (documentId: string) => removePlatformExpertKnowledge(expertId, documentId),
    onSuccess: async () => {
      toast.success(t('experts.removeSuccess'));
      setRemoveDoc(null);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const grantedIds = useMemo(
    () => new Set((grantsQuery.data?.items ?? []).map((g) => g.workspace_id)),
    [grantsQuery.data],
  );
  const pickerWorkspaces = useMemo(
    () => (workspacePickerQuery.data?.items ?? []).filter((ws) => !grantedIds.has(ws.id)),
    [workspacePickerQuery.data, grantedIds],
  );
  const pageRefreshing = expertQuery.isFetching;
  const lifecyclePending =
    publishMutation.isPending || unpublishMutation.isPending || deleteMutation.isPending;
  const accessLabel =
    expert?.availability_mode === 'all_workspaces'
      ? t('experts.access.allWorkspaces')
      : t('experts.access.selectedCount', {
          count: expert?.explicit_workspace_grant_count ?? 0,
        });

  if (expertQuery.isLoading) {
    return <p className="p-8 text-sm text-muted-foreground">{t('common.loading')}</p>;
  }

  if (expertQuery.isError || !expert) {
    return (
      <p className="p-8 text-sm text-destructive" data-testid="expert-detail-error">
        {getErrorMessage(expertQuery.error, t)}
      </p>
    );
  }

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="expert-detail-page"
    >
      <DocumentTitle title={expert.name} />
      <Button variant="ghost" size="sm" asChild className="-ms-2 w-fit">
        <Link to="/experts">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('experts.backToList')}
        </Link>
      </Button>

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-background/85 text-primary shadow-xs md:size-14">
              <Bot className="size-6" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
                {t('experts.detailEyebrow')}
              </p>
              <h1 className="mt-1 break-words text-2xl font-semibold tracking-tight md:text-3xl">
                {expert.name}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <ExpertVisibilityBadge visibility={expert.visibility} />
                <ExpertStatusBadge status={expert.status} />
                {isProtected ? (
                  <Badge variant="info" appearance="light" size="sm">
                    <ShieldCheck className="size-3" aria-hidden />
                    {t('experts.protected')}
                  </Badge>
                ) : null}
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <Sparkles className="size-3.5 shrink-0" aria-hidden />
                  {t(`experts.knowledgeMode.${expert.knowledge_mode}`)}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Globe2 className="size-3.5 shrink-0" aria-hidden />
                  {accessLabel}
                </span>
                <span>
                  {t('experts.updatedAt', {
                    date: formatAdminDate(expert.updated_at, i18n.language),
                  })}
                </span>
              </div>
              {expert.description ? (
                <p className="mt-3 max-w-2xl break-words text-sm leading-6 text-muted-foreground">
                  {expert.description}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void expertQuery.refetch()}
              disabled={pageRefreshing || lifecyclePending}
              className="bg-background/80"
              data-testid="expert-refresh-button"
            >
              <RefreshCw className={cn('size-4', pageRefreshing && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            {!isPublished ? (
              <Button
                onClick={() => setPublishOpen(true)}
                disabled={isProtected || lifecyclePending}
                data-testid="expert-publish-button"
              >
                {t('experts.publish')}
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => setUnpublishOpen(true)}
                disabled={isProtected || lifecyclePending}
                data-testid="expert-unpublish-button"
              >
                {t('experts.unpublish')}
              </Button>
            )}
            {!isProtected ? (
              <Button
                variant="destructive"
                onClick={() => setDeleteOpen(true)}
                disabled={lifecyclePending}
                data-testid="expert-delete-button"
              >
                <Trash2 className="size-4" aria-hidden />
                {t('experts.delete')}
              </Button>
            ) : null}
          </div>
        </div>

        {isProtected ? (
          <div
            className="relative mt-5 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50/80 p-3.5 text-violet-950 dark:border-violet-900 dark:bg-violet-950/45 dark:text-violet-100"
            data-testid="expert-protected-hint"
          >
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="text-sm leading-6">{t('experts.protectedHint')}</p>
          </div>
        ) : null}
      </section>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('experts.sections.instructions')}</CardTitle>
            <CardDescription>{t('experts.createSubtitle')}</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="detail-name">{t('experts.fields.name')}</Label>
            <Input
              id="detail-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isProtected}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="detail-description">{t('experts.fields.description')}</Label>
            <Textarea
              id="detail-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isProtected}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="detail-instructions">{t('experts.fields.instructions')}</Label>
            <Textarea
              id="detail-instructions"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              className="min-h-48 font-mono text-xs"
              data-testid="expert-detail-instructions"
              disabled={isProtected}
            />
          </div>
          {isRag ? (
            <div className="space-y-2">
              <Label>{t('experts.fields.ragConfig')}</Label>
              <RagConfigFields value={ragConfig} onChange={setRagConfig} disabled={isProtected} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('experts.generalModeHint')}</p>
          )}
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isProtected}
            data-testid="expert-save-button"
          >
            {saveMutation.isPending ? t('common.working') : t('common.save')}
          </Button>
        </CardContent>
      </Card>

      {isRag ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t('experts.sections.knowledge')}</CardTitle>
              <CardDescription>{t('experts.knowledgeSubtitle')}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Label
                htmlFor="knowledge-upload"
                className={cn(
                  'inline-flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-4 py-2 text-sm',
                  isProtected && 'pointer-events-none opacity-50',
                )}
              >
                <Upload className="size-4" aria-hidden />
                {t('experts.uploadKnowledge')}
                <input
                  id="knowledge-upload"
                  type="file"
                  className="sr-only"
                  accept={acceptedFileTypes()}
                  disabled={isProtected || uploadMutation.isPending}
                  data-testid="expert-knowledge-upload"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = '';
                    if (!file) return;
                    const result = validateExpertFile(file);
                    if (!result.valid) {
                      toast.error(t(result.errorKey));
                      return;
                    }
                    uploadMutation.mutate(file);
                  }}
                />
              </Label>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void knowledgeQuery.refetch()}
                disabled={knowledgeQuery.isFetching}
              >
                <RefreshCw
                  className={cn('size-4', knowledgeQuery.isFetching && 'animate-spin')}
                  aria-hidden
                />
              </Button>
            </div>

            {(knowledgeQuery.data?.items ?? []).map((item) => (
              <div
                key={item.id}
                className="flex flex-col gap-2 rounded-lg border p-3 md:flex-row md:items-center md:justify-between"
                data-testid={`knowledge-item-${item.document_id}`}
              >
                <div>
                  <p className="font-medium">{item.original_filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.status}
                    {item.progress > 0 && item.status !== 'ready'
                      ? ` · ${Math.round(item.progress * 100)}%`
                      : ''}
                  </p>
                  {item.failure_reason ? (
                    <p className="text-xs text-destructive">{item.failure_reason}</p>
                  ) : null}
                </div>
                <div className="flex gap-2">
                  {item.document_id && item.status === 'failed' ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => reprocessMutation.mutate(item.document_id!)}
                    >
                      {t('experts.retry')}
                    </Button>
                  ) : null}
                  {item.document_id ? (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() =>
                        setRemoveDoc({
                          id: item.document_id!,
                          name: item.original_filename,
                        })
                      }
                    >
                      <Trash2 className="size-4" aria-hidden />
                      {t('experts.remove')}
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}

            {knowledgeQuery.data?.total === 0 ? (
              <p className="text-sm text-muted-foreground">{t('experts.knowledgeEmpty')}</p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('experts.sections.access')}</CardTitle>
            <CardDescription>{t('experts.accessSubtitle')}</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
            <div>
              <p className="font-medium">{t('experts.access.allWorkspacesLabel')}</p>
              <p className="text-sm text-muted-foreground">
                {expert.availability_mode === 'all_workspaces'
                  ? t('common.yes')
                  : t('common.no')}
              </p>
            </div>
            <Button
              variant="outline"
              disabled={isProtected || allWsMutation.isPending}
              onClick={() =>
                allWsMutation.mutate(expert.availability_mode !== 'all_workspaces')
              }
              data-testid="expert-all-workspaces-toggle"
            >
              {expert.availability_mode === 'all_workspaces'
                ? t('experts.access.disableAll')
                : t('experts.access.enableAll')}
            </Button>
          </div>

          {expert.availability_mode !== 'all_workspaces' ? (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="grant-search">{t('experts.access.searchWorkspaces')}</Label>
                <Input
                  id="grant-search"
                  value={pickerSearch}
                  onChange={(e) => {
                    setPickerSearch(e.target.value);
                    setPickerOffset(0);
                  }}
                  placeholder={t('experts.access.searchPlaceholder')}
                  data-testid="expert-grant-search"
                />
                <p className="text-xs text-muted-foreground">{t('experts.access.pickerHint')}</p>
              </div>

              {workspacePickerQuery.isLoading ? (
                <p className="text-sm text-muted-foreground" data-testid="expert-grant-picker-loading">
                  {t('common.loading')}
                </p>
              ) : null}

              {workspacePickerQuery.isError ? (
                <p className="text-sm text-destructive" data-testid="expert-grant-picker-error">
                  {getErrorMessage(workspacePickerQuery.error, t)}
                </p>
              ) : null}

              {pickerWorkspaces.map((ws) => (
                <div
                  key={ws.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                  data-testid={`expert-grant-picker-${ws.id}`}
                >
                  <div>
                    <p className="font-medium">{ws.name}</p>
                    <p className="text-xs text-muted-foreground">{ws.slug}</p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => grantMutation.mutate(ws.id)}
                    disabled={grantMutation.isPending}
                  >
                    {t('experts.grant')}
                  </Button>
                </div>
              ))}

              {!workspacePickerQuery.isLoading &&
              !workspacePickerQuery.isError &&
              pickerWorkspaces.length === 0 ? (
                <p className="text-sm text-muted-foreground" data-testid="expert-grant-picker-empty">
                  {pickerSearch.trim()
                    ? t('experts.access.pickerEmpty')
                    : t('experts.access.pickerNoTenants')}
                </p>
              ) : null}

              {workspacePickerQuery.data && workspacePickerQuery.data.total > PICKER_PAGE_SIZE ? (
                <AdminPagination
                  total={workspacePickerQuery.data.total}
                  limit={workspacePickerQuery.data.limit}
                  offset={workspacePickerQuery.data.offset}
                  onPageChange={setPickerOffset}
                  testId="expert-grant-picker-pagination"
                />
              ) : null}

              <div className="space-y-2">
                <p className="text-sm font-medium">{t('experts.access.grantedWorkspaces')}</p>
                {(grantsQuery.data?.items ?? []).map((grant) => (
                  <div
                    key={grant.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                    data-testid={`grant-row-${grant.workspace_id}`}
                  >
                    <div>
                      <p className="font-medium">{grant.workspace_name}</p>
                      <p className="text-xs text-muted-foreground">{grant.workspace_slug}</p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => revokeMutation.mutate(grant.workspace_id)}
                      disabled={revokeMutation.isPending}
                    >
                      {t('experts.revoke')}
                    </Button>
                  </div>
                ))}
                {(grantsQuery.data?.total ?? 0) === 0 ? (
                  <p className="text-sm text-muted-foreground">{t('experts.access.noGrants')}</p>
                ) : null}
                {grantsQuery.data && grantsQuery.data.total > GRANTS_PAGE_SIZE ? (
                  <AdminPagination
                    total={grantsQuery.data.total}
                    limit={grantsQuery.data.limit}
                    offset={grantsQuery.data.offset}
                    onPageChange={setGrantsOffset}
                    testId="expert-grants-pagination"
                  />
                ) : null}
              </div>
            </>
          ) : null}

          {isPublished &&
          expert.availability_mode !== 'all_workspaces' &&
          (grantsQuery.data?.total ?? 0) === 0 ? (
            <p className="text-sm text-amber-600 dark:text-amber-400">
              {t('experts.publishedNoAccess')}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <AlertDialog open={publishOpen} onOpenChange={setPublishOpen}>
        <AlertDialogContent data-testid="expert-publish-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('experts.publishConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('experts.publishConfirmBody', { name: expert.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending}
              data-testid="expert-publish-confirm"
            >
              {publishMutation.isPending ? t('common.working') : t('experts.publish')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={unpublishOpen} onOpenChange={setUnpublishOpen}>
        <AlertDialogContent data-testid="expert-unpublish-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('experts.unpublishConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('experts.unpublishConfirmBody')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={() => unpublishMutation.mutate()}
              disabled={unpublishMutation.isPending}
            >
              {unpublishMutation.isPending ? t('common.working') : t('experts.unpublish')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent data-testid="expert-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('experts.deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('experts.deleteConfirmBody', { name: expert.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              data-testid="expert-delete-confirm"
            >
              {deleteMutation.isPending ? t('common.working') : t('experts.delete')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={Boolean(removeDoc)} onOpenChange={() => setRemoveDoc(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('experts.removeConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('experts.removeConfirmBody', { name: removeDoc?.name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={() => removeDoc && removeMutation.mutate(removeDoc.id)}
              disabled={removeMutation.isPending}
            >
              {t('experts.remove')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
