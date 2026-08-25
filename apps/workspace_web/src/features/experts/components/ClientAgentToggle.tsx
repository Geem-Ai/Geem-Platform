import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  hasActiveAgentsAiAccess,
  type AgentsAiUsage,
} from '@/services/api/apps';

type ClientAgentToggleProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  usage: AgentsAiUsage | undefined;
  accessLoading: boolean;
  accessError: boolean;
  pending?: boolean;
};

function recoveryKey(usage: AgentsAiUsage | undefined): string {
  if (usage?.access.status === 'expired') {
    return 'experts.clientAgent.renewAccess';
  }
  if (usage?.access.commercially_entitled && !usage.access.installed) {
    return 'experts.clientAgent.reinstallApp';
  }
  return 'experts.clientAgent.purchaseAccess';
}

export function ClientAgentToggle({
  checked,
  onCheckedChange,
  usage,
  accessLoading,
  accessError,
  pending,
}: ClientAgentToggleProps) {
  const { t } = useTranslation();
  const active = hasActiveAgentsAiAccess(usage);
  // Expiry/uninstall makes a stored true value inert, but users must still be
  // able to turn it off. Only a false -> true transition is access-gated.
  const enableBlocked = !checked && !active;
  const disabled = Boolean(pending || enableBlocked);

  return (
    <div className="space-y-3" data-testid="client-agent-toggle-section">
      <label
        htmlFor="expert-client-agent-enabled"
        className={cn(
          'flex items-start justify-between gap-4 rounded-lg border border-border bg-muted/30 p-3.5',
          disabled ? 'cursor-not-allowed' : 'cursor-pointer',
        )}
      >
        <span className="min-w-0 space-y-1">
          <span className="block text-sm font-medium">
            {t('experts.clientAgent.label')}
          </span>
          <span className="block text-xs leading-relaxed text-muted-foreground">
            {t('experts.clientAgent.description')}
          </span>
        </span>
        <span className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center">
          <input
            id="expert-client-agent-enabled"
            type="checkbox"
            role="switch"
            className="peer sr-only"
            checked={checked}
            onChange={(event) => onCheckedChange(event.target.checked)}
            disabled={disabled}
            aria-describedby="expert-client-agent-warning"
            data-testid="client-agent-enabled"
          />
          <span
            className={cn(
              'pointer-events-none absolute inset-0 rounded-full bg-input transition-colors',
              'peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2',
              'peer-disabled:opacity-60',
            )}
          />
          <span
            className={cn(
              'pointer-events-none absolute top-0.5 start-0.5 size-4 rounded-full bg-background shadow-xs',
              'transition-[inset-inline-start] peer-checked:start-[1.125rem] peer-disabled:opacity-70',
            )}
          />
        </span>
      </label>

      <div
        id="expert-client-agent-warning"
        role="note"
        className="flex items-start gap-2 rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2.5 text-xs leading-relaxed text-foreground"
      >
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" aria-hidden />
        <span>{t('experts.clientAgent.securityWarning')}</span>
      </div>

      {!active ? (
        <div
          className="rounded-lg border border-border px-3 py-2.5 space-y-2"
          data-testid="client-agent-access-required"
        >
          <p className="text-xs text-muted-foreground">
            {checked
              ? t('experts.clientAgent.enabledButInactive')
              : accessLoading
                ? t('experts.clientAgent.checkingAccess')
                : accessError
                  ? t('experts.clientAgent.accessCheckFailed')
                  : t('experts.clientAgent.accessRequired')}
          </p>
          {!accessLoading ? (
            <Button asChild variant="outline" size="sm">
              <Link to="/apps/agents-ai">{t(recoveryKey(usage))}</Link>
            </Button>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground" data-testid="client-agent-access-active">
          {t('experts.clientAgent.accessActive')}
        </p>
      )}
    </div>
  );
}
