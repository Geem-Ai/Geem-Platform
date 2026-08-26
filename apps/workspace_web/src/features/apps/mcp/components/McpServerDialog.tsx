import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type {
  McpAuthMode,
  McpOauthStrategy,
  McpServerCreateInput,
} from '@/services/api/mcp';
import { useCreateMcpServer, useStartMcpOauth } from '../hooks/useMcpQueries';

export function McpServerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateMcpServer();
  const oauth = useStartMcpOauth();
  const [displayName, setDisplayName] = useState('');
  const [serverUrl, setServerUrl] = useState('');
  const [authMode, setAuthMode] = useState<McpAuthMode>('none');
  const [staticKind, setStaticKind] = useState<'bearer' | 'header'>('bearer');
  const [headerName, setHeaderName] = useState('Authorization');
  const [secret, setSecret] = useState('');
  const [oauthStrategy, setOauthStrategy] =
    useState<McpOauthStrategy>('cimd');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [sharedAccountAck, setSharedAccountAck] = useState(false);
  const pending = create.isPending || oauth.isPending;

  useEffect(() => {
    if (open) return;
    setDisplayName('');
    setServerUrl('');
    setAuthMode('none');
    setStaticKind('bearer');
    setHeaderName('Authorization');
    setSecret('');
    setOauthStrategy('cimd');
    setClientId('');
    setClientSecret('');
    setSharedAccountAck(false);
    create.reset();
    oauth.reset();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  function buildInput(): McpServerCreateInput {
    let auth: McpServerCreateInput['auth'];
    if (authMode === 'static') {
      auth = {
        mode: 'static',
        header_name:
          staticKind === 'bearer' ? 'Authorization' : headerName.trim(),
        secret,
      };
    } else if (authMode === 'oauth') {
      auth = {
        mode: 'oauth',
        strategy: oauthStrategy,
        client_id:
          oauthStrategy === 'pre_registered' ? clientId.trim() || null : null,
        client_secret:
          oauthStrategy === 'pre_registered' ? clientSecret || null : null,
      };
    } else {
      auth = { mode: 'none' };
    }
    return {
      display_name: displayName.trim() || new URL(serverUrl.trim()).hostname,
      server_url: serverUrl.trim(),
      auth,
    };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!serverUrl.trim() || !sharedAccountAck) return;
    try {
      const server = await create.mutateAsync(buildInput());
      // Secrets stay only in component memory and are cleared before navigation.
      setSecret('');
      setClientSecret('');
      if (server.authorization_url) {
        window.location.assign(server.authorization_url);
        return;
      }
      if (authMode === 'oauth') {
        const result = await oauth.mutateAsync({
          connectionId: server.id,
          returnPath: '/apps/mcp',
        });
        window.location.assign(result.authorization_url);
        return;
      }
      toast.success(t('apps.mcp.serverAdded'));
      onOpenChange(false);
    } catch (error) {
      const code = error instanceof ApiError ? error.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    }
  }

  const staticInvalid =
    authMode === 'static' &&
    (!secret || (staticKind === 'header' && !headerName.trim()));
  const oauthInvalid =
    authMode === 'oauth' &&
    oauthStrategy === 'pre_registered' &&
    !clientId.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" data-testid="mcp-server-dialog">
        <form onSubmit={submit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>{t('apps.mcp.addServer')}</DialogTitle>
            <DialogDescription>{t('apps.mcp.addServerHint')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="mcp-display-name">{t('apps.mcp.displayName')}</Label>
              <Input
                id="mcp-display-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                maxLength={200}
                disabled={pending}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mcp-server-url">{t('apps.mcp.serverUrl')}</Label>
              <Input
                id="mcp-server-url"
                type="url"
                dir="ltr"
                placeholder="https://mcp.example.com"
                value={serverUrl}
                onChange={(event) => setServerUrl(event.target.value)}
                autoComplete="url"
                required
                disabled={pending}
              />
              <p className="text-xs text-muted-foreground">
                {t('apps.mcp.publicHttpsOnly')}
              </p>
            </div>
            <div className="space-y-2">
              <Label>{t('apps.mcp.authMode')}</Label>
              <Select
                value={authMode}
                onValueChange={(value) => setAuthMode(value as McpAuthMode)}
                disabled={pending}
              >
                <SelectTrigger data-testid="mcp-auth-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t('apps.mcp.auth.none')}</SelectItem>
                  <SelectItem value="static">{t('apps.mcp.auth.static')}</SelectItem>
                  <SelectItem value="oauth">{t('apps.mcp.auth.oauth')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {authMode === 'static' ? (
              <div className="rounded-lg border border-border p-3 space-y-3">
                <div className="space-y-2">
                  <Label>{t('apps.mcp.staticKind')}</Label>
                  <Select
                    value={staticKind}
                    onValueChange={(value) =>
                      setStaticKind(value as 'bearer' | 'header')
                    }
                    disabled={pending}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="bearer">{t('apps.mcp.auth.bearer')}</SelectItem>
                      <SelectItem value="header">{t('apps.mcp.auth.header')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {staticKind === 'header' ? (
                  <div className="space-y-2">
                    <Label htmlFor="mcp-header-name">{t('apps.mcp.headerName')}</Label>
                    <Input
                      id="mcp-header-name"
                      dir="ltr"
                      value={headerName}
                      onChange={(event) => setHeaderName(event.target.value)}
                      autoComplete="off"
                      disabled={pending}
                    />
                  </div>
                ) : null}
                <div className="space-y-2">
                  <Label htmlFor="mcp-secret">{t('apps.mcp.secret')}</Label>
                  <Input
                    id="mcp-secret"
                    type="password"
                    dir="ltr"
                    value={secret}
                    onChange={(event) => setSecret(event.target.value)}
                    autoComplete="new-password"
                    disabled={pending}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('apps.mcp.secretWriteOnly')}
                  </p>
                </div>
              </div>
            ) : null}

            {authMode === 'oauth' ? (
              <div className="rounded-lg border border-border p-3 space-y-3">
                <div className="space-y-2">
                  <Label>{t('apps.mcp.oauthStrategy')}</Label>
                  <Select
                    value={oauthStrategy}
                    onValueChange={(value) =>
                      setOauthStrategy(value as McpOauthStrategy)
                    }
                    disabled={pending}
                  >
                    <SelectTrigger data-testid="mcp-oauth-strategy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cimd">{t('apps.mcp.oauth.cimd')}</SelectItem>
                      <SelectItem value="pre_registered">
                        {t('apps.mcp.oauth.preRegistered')}
                      </SelectItem>
                      <SelectItem value="dynamic_registration">
                        {t('apps.mcp.oauth.dynamic')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {oauthStrategy === 'pre_registered' ? (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="mcp-client-id">{t('apps.mcp.clientId')}</Label>
                      <Input
                        id="mcp-client-id"
                        dir="ltr"
                        value={clientId}
                        onChange={(event) => setClientId(event.target.value)}
                        autoComplete="off"
                        disabled={pending}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mcp-client-secret">
                        {t('apps.mcp.clientSecret')}
                      </Label>
                      <Input
                        id="mcp-client-secret"
                        type="password"
                        dir="ltr"
                        value={clientSecret}
                        onChange={(event) => setClientSecret(event.target.value)}
                        autoComplete="new-password"
                        disabled={pending}
                      />
                    </div>
                  </>
                ) : null}
              </div>
            ) : null}

            <label className="flex items-start gap-2 rounded-lg border border-border p-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4"
                checked={sharedAccountAck}
                onChange={(event) => setSharedAccountAck(event.target.checked)}
                disabled={pending}
                data-testid="mcp-shared-account-ack"
              />
              <span>
                <span className="block font-medium">
                  {t('apps.mcp.sharedAccountTitle')}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground leading-relaxed">
                  {t('apps.mcp.sharedAccountDisclosure')}
                </span>
              </span>
            </label>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={
                pending ||
                !serverUrl.trim() ||
                !sharedAccountAck ||
                staticInvalid ||
                oauthInvalid
              }
              data-testid="mcp-server-submit"
            >
              {pending ? t('apps.mcp.connecting') : t('apps.mcp.addServer')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
