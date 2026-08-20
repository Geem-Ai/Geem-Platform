import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type FilterOption = { value: string; labelKey: string };

type AdminListFiltersProps = {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholderKey: string;
  status?: string;
  onStatusChange?: (value: string) => void;
  statusOptions?: FilterOption[];
  secondary?: string;
  onSecondaryChange?: (value: string) => void;
  secondaryOptions?: FilterOption[];
  secondaryLabelKey?: string;
  /** When false, omit the blank "All" option (caller supplies its own all-value). */
  secondaryIncludeBlank?: boolean;
  testIdPrefix: string;
};

export function AdminListFilters({
  search,
  onSearchChange,
  searchPlaceholderKey,
  status = '',
  onStatusChange,
  statusOptions,
  secondary = '',
  onSecondaryChange,
  secondaryOptions,
  secondaryLabelKey,
  secondaryIncludeBlank = true,
  testIdPrefix,
}: AdminListFiltersProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(search);

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
      className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
      data-testid={`${testIdPrefix}-filters`}
    >
      <div className="flex-1 min-w-[12rem]">
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
      {statusOptions && onStatusChange ? (
        <div className="w-full sm:w-40">
          <Label htmlFor={`${testIdPrefix}-status`} className="text-xs text-muted-foreground mb-1 block">
            {t('common.status')}
          </Label>
          <select
            id={`${testIdPrefix}-status`}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            value={status}
            onChange={(e) => onStatusChange(e.target.value)}
            data-testid={`${testIdPrefix}-status`}
          >
            <option value="">{t('common.all')}</option>
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {secondaryOptions && onSecondaryChange ? (
        <div className="w-full sm:w-40">
          <Label
            htmlFor={`${testIdPrefix}-secondary`}
            className="text-xs text-muted-foreground mb-1 block"
          >
            {t(secondaryLabelKey ?? 'common.filter')}
          </Label>
          <select
            id={`${testIdPrefix}-secondary`}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            value={secondary}
            onChange={(e) => onSecondaryChange(e.target.value)}
            data-testid={`${testIdPrefix}-secondary`}
          >
            {secondaryIncludeBlank ? <option value="">{t('common.all')}</option> : null}
            {secondaryOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
    </div>
  );
}
