import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListFilter } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export type AdminFilterField = {
  id: string;
  labelKey: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; labelKey: string }[];
  includeBlank?: boolean;
};

type AdminFilterMenuProps = {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholderKey: string;
  fields: AdminFilterField[];
  onReset: () => void;
  testIdPrefix: string;
};

const selectClassName =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]';

export function AdminFilterMenu({
  search,
  onSearchChange,
  searchPlaceholderKey,
  fields,
  onReset,
  testIdPrefix,
}: AdminFilterMenuProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(search);
  const [open, setOpen] = useState(false);

  const activeFilterCount = useMemo(
    () => fields.filter((field) => Boolean(field.value)).length,
    [fields],
  );
  const hasCustomFilters = Boolean(search) || activeFilterCount > 0;

  useEffect(() => {
    setDraft(search);
  }, [search]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (draft !== search) onSearchChange(draft);
    }, 300);
    return () => window.clearTimeout(handle);
  }, [draft, search, onSearchChange]);

  return (
    <div
      className="flex flex-col gap-2 sm:flex-row sm:items-center"
      data-testid={`${testIdPrefix}-filters`}
    >
      <div className="min-w-0 flex-1">
        <Label htmlFor={`${testIdPrefix}-search`} className="sr-only">
          {t('common.search')}
        </Label>
        <Input
          id={`${testIdPrefix}-search`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t(searchPlaceholderKey)}
          data-testid={`${testIdPrefix}-search`}
        />
      </div>

      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            className="shrink-0 gap-2"
            data-testid={`${testIdPrefix}-filter-menu`}
            aria-label={
              activeFilterCount > 0
                ? t('common.activeFilters', { count: activeFilterCount })
                : t('common.filters')
            }
          >
            <ListFilter className="size-4" aria-hidden />
            <span>{t('common.filters')}</span>
            {activeFilterCount > 0 ? (
              <Badge
                variant="primary"
                appearance="light"
                size="sm"
                className="min-w-5 justify-center px-1.5"
                data-testid={`${testIdPrefix}-filter-count`}
              >
                {activeFilterCount}
              </Badge>
            ) : null}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align="end"
          className="w-72 space-y-3 p-3"
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          <DropdownMenuLabel className="px-0 py-0 text-sm font-medium text-foreground">
            {t('common.filters')}
          </DropdownMenuLabel>
          <div className="space-y-3">
            {fields.map((field) => (
              <div key={field.id} className="space-y-1.5">
                <Label
                  htmlFor={`${testIdPrefix}-${field.id}`}
                  className="text-xs text-muted-foreground"
                >
                  {t(field.labelKey)}
                </Label>
                <select
                  id={`${testIdPrefix}-${field.id}`}
                  className={selectClassName}
                  value={field.value}
                  onChange={(event) => field.onChange(event.target.value)}
                  onPointerDown={(event) => event.stopPropagation()}
                  data-testid={`${testIdPrefix}-${field.id}`}
                >
                  {field.includeBlank !== false ? (
                    <option value="">{t('common.all')}</option>
                  ) : null}
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {t(option.labelKey)}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          {hasCustomFilters ? (
            <>
              <DropdownMenuSeparator className="mx-0" />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className={cn('w-full justify-center')}
                onClick={() => {
                  onReset();
                  setOpen(false);
                }}
                data-testid={`${testIdPrefix}-reset-filters`}
              >
                {t('common.resetFilters')}
              </Button>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
