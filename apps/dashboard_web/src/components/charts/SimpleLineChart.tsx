import { useCallback, useEffect, useId, useMemo, useRef, useState, type WheelEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { CircleHelp, Maximize2, Mouse, MousePointer2, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { formatInteger } from '@/lib/format';

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

const WIDTH = 640;
const HEIGHT = 200;
const PADDING = { top: 14, right: 14, bottom: 30, left: 52 };

function niceScale(maxValue: number, tickCount = 4): { max: number; ticks: number[] } {
  if (maxValue <= 0) {
    return { max: 1, ticks: [0, 1] };
  }
  const roughStep = maxValue / tickCount;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const residual = roughStep / magnitude;
  let niceStep = magnitude;
  if (residual > 5) niceStep = 10 * magnitude;
  else if (residual > 2) niceStep = 5 * magnitude;
  else if (residual > 1) niceStep = 2 * magnitude;

  const niceMax = Math.ceil(maxValue / niceStep) * niceStep;
  const ticks: number[] = [];
  for (let value = 0; value <= niceMax; value += niceStep) {
    ticks.push(value);
  }
  return { max: niceMax, ticks };
}

function clampIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(length - 1, index));
}

export function SimpleLineChart({
  points,
  locale,
  emptyLabel,
  valueLabel,
  'data-testid': testId = 'usage-line-chart',
}: SimpleLineChartProps) {
  const { t } = useTranslation();
  const gradientId = useId().replace(/:/g, '');
  const plotRef = useRef<SVGSVGElement | null>(null);
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(() => Math.max(0, points.length - 1));
  const [brushStartX, setBrushStartX] = useState<number | null>(null);
  const [brushEndX, setBrushEndX] = useState<number | null>(null);
  const [isBrushing, setIsBrushing] = useState(false);

  useEffect(() => {
    setViewStart(0);
    setViewEnd(Math.max(0, points.length - 1));
  }, [points]);

  const pointCount = points.length;
  const safeViewEnd = Math.min(viewEnd, Math.max(0, pointCount - 1));
  const safeViewStart = Math.min(viewStart, safeViewEnd);
  const isZoomed = safeViewStart > 0 || safeViewEnd < pointCount - 1;

  const visiblePoints = useMemo(
    () => points.slice(safeViewStart, safeViewEnd + 1),
    [points, safeViewStart, safeViewEnd],
  );

  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const chart = useMemo(() => {
    if (!visiblePoints.length) {
      return {
        path: '',
        areaClose: '',
        xLabels: [] as string[],
        yTicks: [0],
        yMax: 1,
        coords: [] as { x: number; y: number }[],
      };
    }

    const dataMax = Math.max(...visiblePoints.map((point) => point.value), 0);
    const { max: yMax, ticks: yTicks } = niceScale(dataMax);

    const coords = visiblePoints.map((point, index) => {
      const x =
        visiblePoints.length === 1
          ? PADDING.left + plotWidth / 2
          : PADDING.left + (index / (visiblePoints.length - 1)) * plotWidth;
      const y =
        PADDING.top +
        plotHeight -
        (point.value / yMax) * plotHeight;
      return { x, y };
    });

    const path = coords.map((item, index) => `${index === 0 ? 'M' : 'L'} ${item.x} ${item.y}`).join(' ');
    const baselineY = PADDING.top + plotHeight;
    const areaClose = `${path} L ${coords[coords.length - 1]?.x ?? PADDING.left} ${baselineY} L ${coords[0]?.x ?? PADDING.left} ${baselineY} Z`;

    const tickIndexes = [0, Math.floor((visiblePoints.length - 1) / 2), visiblePoints.length - 1].filter(
      (value, index, arr) => arr.indexOf(value) === index,
    );
    const xLabels = tickIndexes.map((index) =>
      new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(
        new Date(visiblePoints[index].date),
      ),
    );

    return { path, areaClose, xLabels, yTicks, yMax, coords };
  }, [locale, plotHeight, plotWidth, visiblePoints]);

  const visibleRangeLabel = useMemo(() => {
    if (!visiblePoints.length) return null;
    const formatter = new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' });
    const from = formatter.format(new Date(visiblePoints[0].date));
    const to = formatter.format(new Date(visiblePoints[visiblePoints.length - 1].date));
    return from === to ? from : `${from} – ${to}`;
  }, [locale, visiblePoints]);

  const resetZoom = useCallback(() => {
    setViewStart(0);
    setViewEnd(Math.max(0, points.length - 1));
    setBrushStartX(null);
    setBrushEndX(null);
    setIsBrushing(false);
  }, [points.length]);

  const zoomIn = useCallback(() => {
    if (pointCount <= 2) return;
    const range = safeViewEnd - safeViewStart;
    const newRange = Math.max(1, Math.floor(range * 0.55));
    const center = (safeViewStart + safeViewEnd) / 2;
    const half = newRange / 2;
    const nextStart = clampIndex(Math.floor(center - half), pointCount);
    const nextEnd = clampIndex(Math.ceil(center + half), pointCount);
    setViewStart(Math.min(nextStart, nextEnd - 1));
    setViewEnd(Math.max(nextEnd, nextStart + 1));
  }, [pointCount, safeViewEnd, safeViewStart]);

  const zoomOut = useCallback(() => {
    if (pointCount <= 1) return;
    const range = safeViewEnd - safeViewStart;
    const newRange = Math.min(pointCount - 1, Math.ceil(range * 1.6));
    const center = (safeViewStart + safeViewEnd) / 2;
    const half = newRange / 2;
    const nextStart = clampIndex(Math.floor(center - half), pointCount);
    const nextEnd = clampIndex(Math.ceil(center + half), pointCount);
    if (nextStart === 0 && nextEnd === pointCount - 1) {
      resetZoom();
      return;
    }
    setViewStart(nextStart);
    setViewEnd(nextEnd);
  }, [pointCount, resetZoom, safeViewEnd, safeViewStart]);

  const clientXToPlotX = useCallback((clientX: number): number | null => {
    const svg = plotRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const scale = WIDTH / rect.width;
    const x = (clientX - rect.left) * scale;
    if (x < PADDING.left || x > WIDTH - PADDING.right) return null;
    return x;
  }, []);

  const plotXToGlobalIndex = useCallback(
    (plotX: number): number => {
      if (visiblePoints.length <= 1) return safeViewStart;
      const ratio = (plotX - PADDING.left) / plotWidth;
      const localIndex = Math.round(ratio * (visiblePoints.length - 1));
      return clampIndex(safeViewStart + localIndex, pointCount);
    },
    [plotWidth, pointCount, safeViewStart, visiblePoints.length],
  );

  const applyBrushZoom = useCallback(
    (startX: number, endX: number) => {
      const left = Math.min(startX, endX);
      const right = Math.max(startX, endX);
      if (right - left < 8) return;
      const startIndex = plotXToGlobalIndex(left);
      const endIndex = plotXToGlobalIndex(right);
      if (endIndex - startIndex < 1) return;
      setViewStart(Math.min(startIndex, endIndex));
      setViewEnd(Math.max(startIndex, endIndex));
    },
    [plotXToGlobalIndex],
  );

  const handleWheel = useCallback(
    (event: WheelEvent<SVGSVGElement>) => {
      if (pointCount <= 2) return;
      event.preventDefault();
      const plotX = clientXToPlotX(event.clientX);
      if (plotX == null) return;
      const focusIndex = plotXToGlobalIndex(plotX);
      const zoomInWheel = event.deltaY < 0;
      const range = safeViewEnd - safeViewStart;
      const newRange = zoomInWheel
        ? Math.max(1, Math.floor(range * 0.7))
        : Math.min(pointCount - 1, Math.ceil(range * 1.35));
      if (!zoomInWheel && newRange >= pointCount - 1) {
        resetZoom();
        return;
      }
      const focusOffset = focusIndex - safeViewStart;
      const focusRatio = range > 0 ? focusOffset / range : 0.5;
      let nextStart = Math.round(focusIndex - newRange * focusRatio);
      let nextEnd = nextStart + newRange;
      if (nextStart < 0) {
        nextStart = 0;
        nextEnd = newRange;
      }
      if (nextEnd > pointCount - 1) {
        nextEnd = pointCount - 1;
        nextStart = nextEnd - newRange;
      }
      setViewStart(clampIndex(nextStart, pointCount));
      setViewEnd(clampIndex(nextEnd, pointCount));
    },
    [
      clientXToPlotX,
      plotXToGlobalIndex,
      pointCount,
      resetZoom,
      safeViewEnd,
      safeViewStart,
    ],
  );

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

  const brushLeft =
    brushStartX != null && brushEndX != null
      ? Math.min(brushStartX, brushEndX)
      : null;
  const brushWidth =
    brushStartX != null && brushEndX != null
      ? Math.abs(brushEndX - brushStartX)
      : 0;

  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {isZoomed && visibleRangeLabel ? (
            <span
              className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
              data-testid="chart-zoom-range"
            >
              {t('usage.chartZoomRange', { range: visibleRangeLabel })}
            </span>
          ) : (
            <>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground">
                <MousePointer2 className="size-3.5 shrink-0" aria-hidden />
                {t('usage.chartZoomDrag')}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground">
                <Mouse className="size-3.5 shrink-0" aria-hidden />
                {t('usage.chartZoomScroll')}
              </span>
            </>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 w-8 px-0 text-muted-foreground"
                aria-label={t('usage.chartZoomHelpTitle')}
                data-testid="chart-zoom-help"
              >
                <CircleHelp className="size-4" aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom" align="end" className="max-w-xs space-y-1.5 p-3 text-start">
              <p className="font-medium text-foreground">{t('usage.chartZoomHelpTitle')}</p>
              <ul className="list-disc space-y-1 ps-4 text-muted-foreground">
                <li>{t('usage.chartZoomHelpDrag')}</li>
                <li>{t('usage.chartZoomHelpScroll')}</li>
                <li>{t('usage.chartZoomHelpButtons')}</li>
              </ul>
            </TooltipContent>
          </Tooltip>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2"
            onClick={zoomIn}
            aria-label={t('usage.chartZoomIn')}
            data-testid="chart-zoom-in"
          >
            <ZoomIn className="size-4" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2"
            onClick={zoomOut}
            aria-label={t('usage.chartZoomOut')}
            data-testid="chart-zoom-out"
          >
            <ZoomOut className="size-4" aria-hidden />
          </Button>
          {isZoomed ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 gap-1 px-2"
              onClick={resetZoom}
              aria-label={t('usage.chartResetZoom')}
              data-testid="chart-reset-zoom"
            >
              <Maximize2 className="size-4" aria-hidden />
              <span className="text-xs">{t('usage.chartResetZoom')}</span>
            </Button>
          ) : null}
        </div>
      </div>

      <svg
        ref={plotRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-52 w-full touch-none select-none"
        role="img"
        aria-label={valueLabel}
        onWheel={handleWheel}
        onPointerDown={(event) => {
          const x = clientXToPlotX(event.clientX);
          if (x == null) return;
          plotRef.current?.setPointerCapture(event.pointerId);
          setIsBrushing(true);
          setBrushStartX(x);
          setBrushEndX(x);
        }}
        onPointerMove={(event) => {
          if (!isBrushing) return;
          const x = clientXToPlotX(event.clientX);
          if (x == null) return;
          setBrushEndX(x);
        }}
        onPointerUp={(event) => {
          if (!isBrushing || brushStartX == null || brushEndX == null) return;
          plotRef.current?.releasePointerCapture(event.pointerId);
          applyBrushZoom(brushStartX, brushEndX);
          setIsBrushing(false);
          setBrushStartX(null);
          setBrushEndX(null);
        }}
        onPointerLeave={() => {
          if (!isBrushing) return;
          if (brushStartX != null && brushEndX != null) {
            applyBrushZoom(brushStartX, brushEndX);
          }
          setIsBrushing(false);
          setBrushStartX(null);
          setBrushEndX(null);
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {chart.yTicks.map((tick) => {
          const y = PADDING.top + plotHeight - (tick / chart.yMax) * plotHeight;
          return (
            <g key={tick}>
              <line
                x1={PADDING.left}
                y1={y}
                x2={WIDTH - PADDING.right}
                y2={y}
                stroke="var(--border)"
                strokeOpacity={0.55}
                strokeDasharray="4 4"
              />
              <text
                x={PADDING.left - 8}
                y={y + 4}
                textAnchor="end"
                className="fill-muted-foreground text-[10px]"
              >
                {formatInteger(tick, locale)}
              </text>
            </g>
          );
        })}

        <path d={chart.areaClose} fill={`url(#${gradientId})`} />
        <path
          d={chart.path}
          fill="none"
          stroke="var(--chart-1)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {brushLeft != null && brushWidth > 0 ? (
          <rect
            x={brushLeft}
            y={PADDING.top}
            width={brushWidth}
            height={plotHeight}
            fill="var(--primary)"
            fillOpacity={0.12}
            stroke="var(--primary)"
            strokeOpacity={0.45}
            pointerEvents="none"
          />
        ) : null}

        <rect
          x={PADDING.left}
          y={PADDING.top}
          width={plotWidth}
          height={plotHeight}
          fill="transparent"
          className="cursor-crosshair"
        />
      </svg>

      <div
        className="flex justify-between ps-[3.25rem] text-xs text-muted-foreground"
        data-testid="chart-x-labels"
      >
        {chart.xLabels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <p className="sr-only">
        {valueLabel}: {visiblePoints.map((point) => `${point.date} ${point.value}`).join(', ')}
      </p>
    </div>
  );
}
