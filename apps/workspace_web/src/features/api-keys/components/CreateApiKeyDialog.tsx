import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  API_KEY_SCOPE_AGENT_WRITE,
  API_KEY_SCOPE_CHAT_WRITE,
  type CreatedApiKey,
} from '@/services/api/api-keys';
import { hasActiveAgentsAiAccess } from '@/services/api/apps';
import { useAgentsAiUsage } from '@/features/apps/hooks/useAppsQueries';
import { useCreateApiKey } from '../hooks/useApiKeyQueries';

type CreateApiKeyDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (created: CreatedApiKey) => void;
};

export function CreateApiKeyDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateApiKeyDialogProps) {
  const { t } = useTranslation();
  const create = useCreateApiKey();
  const agentsAiUsage = useAgentsAiUsage(open);
  const [name, setName] = useState('');
  const [expiresMode, setExpiresMode] = useState<'never' | 'date'>('never');
  const [expiresLocal, setExpiresLocal] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [agentScope, setAgentScope] = useState(false);
  const agentScopeAvailable = hasActiveAgentsAiAccess(agentsAiUsage.data);

  useEffect(() => {
    if (!open) return;
    setName('');
    setExpiresMode('never');
    setExpiresLocal('');
    setErrorKey(null);
    setAgentScope(false);
    create.reset();
    // Intentionally reset only when the dialog opens — not on mutation identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setErrorKey('apiKeys.nameRequired');
      return;
    }
    let expiresAt: string | null = null;
    if (expiresMode === 'date') {
      if (!expiresLocal) {
        setErrorKey('apiKeys.expirationRequired');
        return;
      }
      const when = new Date(expiresLocal);
      if (Number.isNaN(when.getTime()) || when.getTime() <= Date.now()) {
        setErrorKey('apiKeys.expirationFuture');
        return;
      }
      expiresAt = when.toISOString();
    }
    setErrorKey(null);
    try {
      const created = await create.mutateAsync({
        name: trimmed,
        scopes: [
          API_KEY_SCOPE_CHAT_WRITE,
          ...(agentScope && agentScopeAvailable
            ? [API_KEY_SCOPE_AGENT_WRITE]
            : []),
        ],
        expires_at: expiresAt,
      });
      onCreated(created);
      create.reset();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorKey(errorMessageKey(err.code));
      } else {
        setErrorKey('errors.generic');
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !create.isPending && onOpenChange(next)}>
      <DialogContent data-testid="create-api-key-dialog">
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t('apiKeys.createTitle')}</DialogTitle>
            <DialogDescription>{t('apiKeys.createDescription')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="api-key-name">{t('apiKeys.name')}</Label>
            <Input
              id="api-key-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('apiKeys.namePlaceholder')}
              maxLength={100}
              autoFocus
              data-testid="api-key-name-input"
            />
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">{t('apiKeys.scope')}</p>
            <p className="text-sm text-muted-foreground">{t('apiKeys.scopeChatWrite')}</p>
            <p className="text-xs font-mono text-muted-foreground" dir="ltr">
              {API_KEY_SCOPE_CHAT_WRITE}
            </p>
            <label
              htmlFor="api-key-agent-scope"
              className={`mt-3 flex items-start gap-2 rounded-lg border border-border p-3 ${
                agentScopeAvailable ? 'cursor-pointer' : 'cursor-not-allowed opacity-70'
              }`}
            >
              <input
                id="api-key-agent-scope"
                type="checkbox"
                className="mt-0.5 size-4 shrink-0 accent-primary"
                checked={agentScope}
                onChange={(event) => setAgentScope(event.target.checked)}
                disabled={!agentScopeAvailable || create.isPending}
                data-testid="api-key-agent-scope"
              />
              <span className="min-w-0 space-y-1">
                <span className="block text-sm font-medium">
                  {t('apiKeys.scopeAgentWrite')}
                </span>
                <span className="block text-xs leading-relaxed text-muted-foreground">
                  {t('apiKeys.scopeAgentWriteHint')}
                </span>
                <code dir="ltr" className="block text-xs font-mono text-muted-foreground">
                  {API_KEY_SCOPE_AGENT_WRITE}
                </code>
              </span>
            </label>
            {!agentScopeAvailable ? (
              <p className="text-xs text-muted-foreground" data-testid="api-key-agent-scope-gate">
                {agentsAiUsage.isLoading
                  ? t('apiKeys.scopeAgentChecking')
                  : agentsAiUsage.isError
                    ? t('apiKeys.scopeAgentCheckFailed')
                    : t('apiKeys.scopeAgentAccessRequired')}{' '}
                {!agentsAiUsage.isLoading ? (
                  <Link
                    to="/apps/agents-ai"
                    className="font-medium text-primary hover:underline"
                  >
                    {t('apiKeys.manageAgentsAi')}
                  </Link>
                ) : null}
              </p>
            ) : null}
            <p className="text-xs text-muted-foreground">
              {t('apiKeys.scopeReissueHint')}
            </p>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t('apiKeys.expiration')}</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="api-key-expires"
                checked={expiresMode === 'never'}
                onChange={() => setExpiresMode('never')}
              />
              {t('apiKeys.neverExpires')}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="api-key-expires"
                checked={expiresMode === 'date'}
                onChange={() => setExpiresMode('date')}
              />
              {t('apiKeys.expiresOn')}
            </label>
            {expiresMode === 'date' ? (
              <Input
                type="datetime-local"
                value={expiresLocal}
                onChange={(e) => setExpiresLocal(e.target.value)}
                data-testid="api-key-expires-input"
              />
            ) : null}
          </fieldset>

          {errorKey ? (
            <p className="text-sm text-destructive" data-testid="create-api-key-error">
              {t(errorKey)}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={create.isPending}
              onClick={() => onOpenChange(false)}
            >
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={create.isPending} data-testid="create-api-key-submit">
              {create.isPending ? t('apiKeys.creating') : t('apiKeys.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
