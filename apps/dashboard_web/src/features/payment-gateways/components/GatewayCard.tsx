import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle2,
  CircleAlert,
  Clock3,
  CreditCard,
  KeyRound,
  Settings2,
  ShoppingBag,
  Zap,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { cn } from '@/lib/utils';
import type { PlatformPaymentGatewayListItem } from '@/services/api/types';

type GatewayCardProps = {
  gateway: PlatformPaymentGatewayListItem;
  locale: string;
  onConfigure: () => void;
  onActivate: () => void;
};

export function GatewayCard({
  gateway,
  locale,
  onConfigure,
  onActivate,
}: GatewayCardProps) {
  const { t } = useTranslation();
  const isActive = gateway.enabled;
  const isNoop = gateway.code === 'noop';
  const creds = gateway.credential_field_status;
  const canActivate = Boolean(gateway.id && gateway.configured && !gateway.enabled);

  return (
    <Card
      data-testid={`gateway-card-${gateway.code}`}
      className={cn(
        'overflow-hidden transition-shadow hover:shadow-md',
        isActive && 'border-primary/40 ring-1 ring-primary/20 shadow-sm',
      )}
    >
      <CardHeader className="items-start gap-4 py-4">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span
            className={cn(
              'flex size-11 shrink-0 items-center justify-center rounded-xl',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground',
            )}
          >
            <CreditCard className="size-5" aria-hidden />
          </span>
          <CardHeading className="min-w-0">
            <CardTitle className="text-base">{gateway.display_name}</CardTitle>
            <CardDescription className="font-mono text-xs">{gateway.code}</CardDescription>
          </CardHeading>
        </div>
        <CardToolbar className="flex-wrap justify-end">
          {isActive ? (
            <Badge
              variant="success"
              appearance="light"
              data-testid={`gateway-active-${gateway.code}`}
            >
              <Zap className="size-3" aria-hidden />
              {t('paymentGateways.active')}
            </Badge>
          ) : (
            <Badge variant="outline" appearance="outline">
              {t('paymentGateways.inactive')}
            </Badge>
          )}
          {gateway.configured ? (
            <Badge variant="success" appearance="outline">
              <CheckCircle2 className="size-3" aria-hidden />
              {t('paymentGateways.configured')}
            </Badge>
          ) : (
            <Badge variant="warning" appearance="outline">
              <CircleAlert className="size-3" aria-hidden />
              {t('paymentGateways.notConfigured')}
            </Badge>
          )}
        </CardToolbar>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {isActive ? (
          <div className="rounded-lg border border-success/20 bg-success/5 px-3 py-2 text-xs text-success-accent dark:text-success">
            {t('paymentGateways.card.routingCheckouts')}
          </div>
        ) : gateway.configured ? (
          <p className="text-xs text-muted-foreground">{t('paymentGateways.card.notRouting')}</p>
        ) : (
          <p className="text-xs text-muted-foreground">
            {isNoop
              ? t('paymentGateways.card.noopDescription')
              : t('paymentGateways.card.unconfiguredDescription')}
          </p>
        )}

        {gateway.id ? (
          <dl className="grid gap-2 sm:grid-cols-2">
            {gateway.test_mode != null ? (
              <MetaRow
                icon={Settings2}
                label={t('paymentGateways.card.modeLabel')}
                value={
                  <Badge
                    variant={gateway.test_mode ? 'warning' : 'success'}
                    appearance="light"
                    size="sm"
                  >
                    {gateway.test_mode
                      ? t('paymentGateways.testMode')
                      : t('paymentGateways.liveMode')}
                  </Badge>
                }
              />
            ) : null}
            <MetaRow
              icon={ShoppingBag}
              label={t('paymentGateways.card.purchasesLabel')}
              value={t('paymentGateways.referenced', {
                count: gateway.referenced_purchases_count,
              })}
            />
            {gateway.in_flight_purchases_count > 0 ? (
              <MetaRow
                icon={CircleAlert}
                label={t('paymentGateways.card.inFlightLabel')}
                value={t('paymentGateways.inFlight', {
                  count: gateway.in_flight_purchases_count,
                })}
                tone="warning"
              />
            ) : null}
            {gateway.updated_at ? (
              <MetaRow
                icon={Clock3}
                label={t('paymentGateways.card.lastUpdated')}
                value={formatAdminDate(gateway.updated_at, locale)}
              />
            ) : null}
          </dl>
        ) : null}

        {gateway.id && gateway.code === 'clickpay' ? (
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              {t('paymentGateways.card.credentials')}
            </p>
            <div className="flex flex-wrap gap-2">
              <CredentialPill
                icon={KeyRound}
                label={t('paymentGateways.profileId')}
                configured={Boolean(creds.profile_id_configured)}
                detail={creds.profile_id ?? undefined}
              />
              <CredentialPill
                icon={KeyRound}
                label={t('paymentGateways.serverKey')}
                configured={Boolean(creds.server_key_configured)}
              />
            </div>
          </div>
        ) : null}
      </CardContent>

      <CardFooter className="flex flex-wrap gap-2 py-4">
        <Button
          size="sm"
          variant={gateway.id ? 'outline' : 'primary'}
          onClick={onConfigure}
          data-testid={`gateway-configure-${gateway.code}`}
        >
          <Settings2 className="size-3.5" aria-hidden />
          {gateway.id ? t('paymentGateways.configure') : t('paymentGateways.addConfiguration')}
        </Button>
        {canActivate ? (
          <Button
            size="sm"
            onClick={onActivate}
            data-testid={`gateway-activate-${gateway.code}`}
          >
            <Zap className="size-3.5" aria-hidden />
            {t('paymentGateways.setActive')}
          </Button>
        ) : null}
      </CardFooter>
    </Card>
  );
}

function MetaRow({
  icon: Icon,
  label,
  value,
  tone = 'default',
}: {
  icon: typeof Settings2;
  label: string;
  value: ReactNode;
  tone?: 'default' | 'warning';
}) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-background/60 px-3 py-2">
      <Icon
        className={cn(
          'mt-0.5 size-3.5 shrink-0',
          tone === 'warning' ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground',
        )}
        aria-hidden
      />
      <div className="min-w-0">
        <dt className="text-[0.6875rem] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </dt>
        <dd
          className={cn(
            'mt-0.5 text-sm',
            tone === 'warning' && 'font-medium text-amber-700 dark:text-amber-300',
          )}
        >
          {value}
        </dd>
      </div>
    </div>
  );
}

function CredentialPill({
  icon: Icon,
  label,
  configured,
  detail,
}: {
  icon: typeof KeyRound;
  label: string;
  configured: boolean;
  detail?: string;
}) {
  const { t } = useTranslation();

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
        configured
          ? 'border-success/30 bg-success/5 text-success-accent dark:text-success'
          : 'border-border bg-background text-muted-foreground',
      )}
    >
      <Icon className="size-3" aria-hidden />
      <span className="font-medium">{label}</span>
      {configured ? (
        <>
          <CheckCircle2 className="size-3" aria-hidden />
          {detail ? <span className="font-mono text-[0.6875rem] opacity-80">{detail}</span> : null}
        </>
      ) : (
        <span>{t('paymentGateways.card.credentialMissing')}</span>
      )}
    </span>
  );
}
