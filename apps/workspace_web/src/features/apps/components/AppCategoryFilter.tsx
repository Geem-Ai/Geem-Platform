import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { AppCategory } from '@/services/api/apps';

export function AppCategoryFilter({
  categories,
  value,
  onChange,
}: {
  categories: AppCategory[];
  value: string | null;
  onChange: (slug: string | null) => void;
}) {
  const { t } = useTranslation();
  const chips: { slug: string | null; label: string }[] = [
    { slug: null, label: t('apps.filters.all') },
    ...categories.map((c) => ({
      slug: c.slug,
      label: t(c.name_key, { defaultValue: c.slug }),
    })),
  ];

  return (
    <div
      data-testid="apps-category-filter"
      className="flex flex-wrap gap-2"
      role="tablist"
      aria-label={t('apps.filters.label')}
    >
      {chips.map((chip) => {
        const active = value === chip.slug;
        return (
          <Button
            key={chip.slug ?? 'all'}
            type="button"
            size="sm"
            variant={active ? 'primary' : 'outline'}
            role="tab"
            aria-selected={active}
            className={cn('rounded-full', active && 'shadow-xs')}
            onClick={() => onChange(chip.slug)}
          >
            {chip.label}
          </Button>
        );
      })}
    </div>
  );
}
