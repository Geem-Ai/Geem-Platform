import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

type Point = {
  date: string;
  value: number;
};

type SimpleLineChartProps = {
  points: Point[];
  locale: string;
  emptyLabel: string;
  valueLabel?: string;
  'data-testid'?: string;
};

export function SimpleLineChart({
  points,
  locale,
  emptyLabel,
  valueLabel,
  'data-testid': testId = 'usage-line-chart',
}: SimpleLineChartProps) {
  const { path, labels } = useMemo(() => {
    if (!points.length) {
      return { path: '', labels: [] as string[], max: 0 };
    }
    const maxValue = Math.max(...points.map((point) => point.value), 1);
    const width = 640;
    const height = 180;
    const padding = 12;
    const coords = points.map((point, index) => {
      const x =
        points.length === 1
          ? width / 2
          : padding + (index / (points.length - 1)) * (width - padding * 2);
      const y = height - padding - (point.value / maxValue) * (height - padding * 2);
      return { x, y, point };
    });
    const d = coords.map((item, index) => `${index === 0 ? 'M' : 'L'} ${item.x} ${item.y}`).join(' ');
    const tickIndexes = [0, Math.floor((points.length - 1) / 2), points.length - 1].filter(
      (value, index, arr) => arr.indexOf(value) === index,
    );
    const chartLabels = tickIndexes.map((index) =>
      new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(
        new Date(points[index].date),
      ),
    );
    return { path: d, labels: chartLabels };
  }, [locale, points]);

  if (!points.length) {
    return (
      <div
        className="flex h-48 items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground"
        data-testid={testId}
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid={testId}>
      <svg viewBox="0 0 640 180" className="h-48 w-full" role="img" aria-label={valueLabel}>
        <defs>
          <linearGradient id="usage-line-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${path} L 628 168 L 12 168 Z`} fill="url(#usage-line-fill)" />
        <path d={path} fill="none" stroke="var(--chart-1)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground">
        {labels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      <p className="sr-only">
        {valueLabel}: {points.map((point) => `${point.date} ${point.value}`).join(', ')}
      </p>
    </div>
  );
}
