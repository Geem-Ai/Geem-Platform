import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Bot,
  ChevronRight,
  Globe2,
  Plus,
  RefreshCw,
  SearchX,
  Sparkles,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminFilterMenu } from '@/components/shared/AdminFilterMenu';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { ExpertStatusBadge, ExpertVisibilityBadge } from '@/components/shared/StatusBadges';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformExperts, platformQueryKeys } from '@/services/api/platform';
import type { PlatformExpertListItem } from '@/services/api/types';

const PAGE_SIZE = 25;

export function ExpertsPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [knowledgeMode, setKnowledgeMode] = useState('');
  const [published, setPublished] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      knowledge_mode: knowledgeMode || undefined,
      published:
        published === 'published' ? true : published === 'draft' ? false : undefined,
    }),
    [offset, search, status, knowledgeMode, published],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.experts(filters),
    queryFn: () => fetchPlatformExperts(filters),
  });

  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setKnowledgeMode('');
    setPublished('');
    setOffset(0);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="experts-page"
    >
      <DocumentTitle title={t('experts.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <Bot className="size-3.5" aria-hidden />
              {t('experts.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('experts.title')}
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('experts.subtitle')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              data-testid="experts-refresh"
            >
              <RefreshCw className={cn('size-4', query.isFetching && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            <Button asChild data-testid="experts-create-button">
              <Link to="/experts/new">
                <Plus className="size-4" aria-hidden />
                {t('experts.create')}
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('experts.inventoryTitle')}</CardTitle>
            <CardDescription>{t('experts.inventorySubtitle')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            <AdminFilterMenu
              search={search}
              onSearchChange={(value) => {
                setSearch(value);
                setOffset(0);
              }}
              searchPlaceholderKey="experts.searchPlaceholder"
              fields={[
                {
                  id: 'status',
                  labelKey: 'common.status',
                  value: status,
                  onChange: (value) => {
                    setStatus(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'draft', labelKey: 'experts.status.draft' },
                    { value: 'ready', labelKey: 'experts.status.ready' },
                    { value: 'processing', labelKey: 'experts.status.processing' },
                    { value: 'failed', labelKey: 'experts.status.failed' },
                    { value: 'disabled', labelKey: 'experts.status.disabled' },
                  ],
                },
                {
                  id: 'secondary',
                  labelKey: 'experts.filters.knowledgeMode',
                  value: knowledgeMode,
                  onChange: (value) => {
                    setKnowledgeMode(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'rag', labelKey: 'experts.knowledgeMode.rag' },
                    { value: 'general', labelKey: 'experts.knowledgeMode.general' },
                  ],
                },
                {
                  id: 'published',
                  labelKey: 'experts.filters.publication',
                  value: published,
                  onChange: (value) => {
                    setPublished(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'published', labelKey: 'experts.visibility.published' },
                    { value: 'draft', labelKey: 'experts.visibility.draft' },
                  ],
                },
              ]}
              onReset={resetFilters}
              testIdPrefix="experts"
            />
          </CardToolbar>
        </CardHeader>
        <CardContent className="space-y-4">
          {query.isError ? (
            <p className="text-sm text-destructive" data-testid="experts-error">
              {getErrorMessage(query.error, t)}
            </p>
          ) : null}

          {query.isLoading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : null}

          {query.data && query.data.items.length === 0 ? (
            <div
              className="flex flex-col items-center gap-3 py-12 text-center"
              data-testid="experts-empty"
            >
              <SearchX className="size-10 text-muted-foreground/60" aria-hidden />
              <p className="text-sm text-muted-foreground">{t('experts.empty')}</p>
            </div>
          ) : null}

          {query.data?.items.map((expert) => (
            <ExpertRow key={expert.id} expert={expert} locale={i18n.language} />
          ))}

          {query.data ? (
            <AdminPagination
              total={query.data.total}
              limit={query.data.limit}
              offset={query.data.offset}
              onPageChange={setOffset}
              testId="experts-pagination"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function ExpertRow({ expert, locale }: { expert: PlatformExpertListItem; locale: string }) {
  const { t } = useTranslation();
  const accessLabel =
    expert.availability_mode === 'all_workspaces'
      ? t('experts.access.allWorkspaces')
      : t('experts.access.selectedCount', { count: expert.explicit_workspace_grant_count });

  return (
    <Link
      to={`/experts/${expert.id}`}
      className="flex flex-col gap-3 rounded-xl border border-border p-4 transition-colors hover:bg-muted/30 md:flex-row md:items-center md:justify-between"
      data-testid={`expert-row-${expert.id}`}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{expert.name}</span>
          <ExpertVisibilityBadge visibility={expert.visibility} />
          <ExpertStatusBadge status={expert.status} />
          {expert.is_protected ? (
            <Badge variant="info" appearance="light" size="sm">
              {t('experts.protected')}
            </Badge>
          ) : null}
        </div>
        {expert.description ? (
          <p className="line-clamp-2 text-sm text-muted-foreground">{expert.description}</p>
        ) : null}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Sparkles className="size-3" aria-hidden />
            {t(`experts.knowledgeMode.${expert.knowledge_mode}`)}
          </span>
          <span>
            {t('experts.knowledgeCount', { count: expert.knowledge_document_count })}
          </span>
          <span className="inline-flex items-center gap-1">
            <Globe2 className="size-3" aria-hidden />
            {accessLabel}
          </span>
          <span>{formatAdminDate(expert.updated_at, locale)}</span>
        </div>
      </div>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground rtl:rotate-180" aria-hidden />
    </Link>
  );
}
