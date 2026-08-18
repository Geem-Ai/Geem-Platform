import type { Meter } from '@/services/api/usage';

/** UI presentation thresholds only — not entitlement/business limits. */
export type QuotaWarningLevel =
  | 'normal'
  | 'approaching'
  | 'critical'
  | 'exhausted';

/** Backend uses 0 for fail-closed / no allowance. Negative means unlimited. */
export function isUnlimitedLimit(limit: number): boolean {
  return limit < 0;
}

export function meterPercentage(
  used: number,
  limit: number,
  reserved = 0,
): number {
  if (isUnlimitedLimit(limit)) return 0;
  if (limit <= 0) return 100;
  const consumed =
    Math.max(0, Number.isFinite(used) ? used : 0) +
    Math.max(0, Number.isFinite(reserved) ? reserved : 0);
  if (consumed <= 0) return 0;
  return Math.min(100, Math.max(0, (consumed / limit) * 100));
}

export function quotaWarningLevel(
  used: number,
  limit: number,
  remaining: number,
  reserved = 0,
): QuotaWarningLevel {
  if (isUnlimitedLimit(limit)) return 'normal';
  if (limit <= 0 || remaining <= 0) return 'exhausted';
  const pct = meterPercentage(used, limit, reserved);
  if (pct >= 100) return 'exhausted';
  if (pct >= 95) return 'critical';
  if (pct >= 80) return 'approaching';
  return 'normal';
}

export function meterWarningLevel(meter: Meter): QuotaWarningLevel {
  return quotaWarningLevel(
    meter.used,
    meter.limit,
    meter.remaining,
    meter.reserved,
  );
}

const LEVEL_RANK: Record<QuotaWarningLevel, number> = {
  normal: 0,
  approaching: 1,
  critical: 2,
  exhausted: 3,
};

export function worstWarningLevel(
  levels: readonly QuotaWarningLevel[],
): QuotaWarningLevel {
  return levels.reduce<QuotaWarningLevel>(
    (worst, level) =>
      LEVEL_RANK[level] > LEVEL_RANK[worst] ? level : worst,
    'normal',
  );
}

export function formatPeriodDateTime(iso: string | null, locale: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function formatPeriodDate(iso: string | null, locale: string): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(date);
}

export function formatRelativeTime(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const deltaSec = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(deltaSec);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (abs < 60) return rtf.format(Math.round(deltaSec), 'second');
  if (abs < 3600) return rtf.format(Math.round(deltaSec / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(deltaSec / 3600), 'hour');
  if (abs < 86400 * 30) return rtf.format(Math.round(deltaSec / 86400), 'day');
  return rtf.format(Math.round(deltaSec / (86400 * 30)), 'month');
}

export const DAY_MS = 86_400_000;

export type RemainingHoursMinutes = {
  days: number;
  hours: number;
  minutes: number;
  totalMs: number;
};

/** Whole days / hours / minutes until `iso`. Values are 0 when the instant is past. */
export function remainingHoursMinutes(
  iso: string | null,
  now = Date.now(),
): RemainingHoursMinutes | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const totalMs = Math.max(0, date.getTime() - now);
  const totalMinutes = Math.floor(totalMs / 60_000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor(totalMinutes / 60) % 24;
  return {
    days,
    hours,
    minutes: totalMinutes % 60,
    totalMs,
  };
}

export function quotaLevelBadgeVariant(
  level: QuotaWarningLevel,
): 'secondary' | 'warning' | 'destructive' {
  if (level === 'exhausted' || level === 'critical') return 'destructive';
  if (level === 'approaching') return 'warning';
  return 'secondary';
}

export function quotaProgressClass(level: QuotaWarningLevel): string {
  if (level === 'exhausted' || level === 'critical') return 'bg-destructive';
  if (level === 'approaching') {
    return 'bg-[var(--color-warning-accent,var(--color-yellow-500))]';
  }
  return 'bg-primary';
}

const BYTE_UNITS = ['bytes', 'kb', 'mb', 'gb', 'tb'] as const;

export type ByteUnitKey = (typeof BYTE_UNITS)[number];

export function formatBytesParts(bytes: number): {
  value: number;
  unit: ByteUnitKey;
} {
  const safe = Math.max(0, Number.isFinite(bytes) ? bytes : 0);
  if (safe < 1024) return { value: safe, unit: 'bytes' };
  let value = safe;
  let idx = 0;
  while (value >= 1024 && idx < BYTE_UNITS.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return { value, unit: BYTE_UNITS[idx] };
}

export function formatCount(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(Math.max(0, Math.round(value)));
}

export function formatBytesLabel(
  bytes: number,
  locale: string,
  unitLabel: (unit: ByteUnitKey) => string,
): string {
  const { value, unit } = formatBytesParts(bytes);
  const formatted =
    unit === 'bytes'
      ? formatCount(value, locale)
      : value >= 10
        ? formatCount(Math.round(value), locale)
        : new Intl.NumberFormat(locale, {
            maximumFractionDigits: 1,
          }).format(value);
  return `${formatted} ${unitLabel(unit)}`;
}
