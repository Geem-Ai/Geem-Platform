import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
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
import { API_KEY_SCOPE_CHAT_WRITE, type CreatedApiKey } from '@/services/api/api-keys';
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
  const [name, setName] = useState('');
  const [expiresMode, setExpiresMode] = useState<'never' | 'date'>('never');
  const [expiresLocal, setExpiresLocal] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName('');
    setExpiresMode('never');
    setExpiresLocal('');
    setErrorKey(null);
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
        scopes: [API_KEY_SCOPE_CHAT_WRITE],
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
