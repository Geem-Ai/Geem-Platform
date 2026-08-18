import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Copy, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input, inputVariants } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { ExpertPickerDialog } from '@/features/chat/components/ExpertPickerDialog';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';
import {
  disconnectChatWidget,
  getChatWidget,
  updateChatWidget,
  type CatalogApp,
  type ChatWidgetInstance,
} from '@/services/api/apps';

function originsToText(origins: string[]): string {
  return origins.join('\n');
}

function textToOrigins(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function ChatWidgetConfigDialog({
  open,
  onOpenChange,
  app,
  canManage,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  app: CatalogApp;
  canManage: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const widgetQuery = useQuery({
    queryKey: ['chat-widget', workspaceId, app.slug],
    queryFn: getChatWidget,
    enabled: open && Boolean(workspaceId),
  });
  const expertsQuery = useExperts();

  const [expertId, setExpertId] = useState<string | null>(null);
  const [title, setTitle] = useState('Geem');
  const [subtitle, setSubtitle] = useState('');
  const [greeting, setGreeting] = useState('');
  const [logoUrl, setLogoUrl] = useState('');
  const [locale, setLocale] = useState('ar');
  const [position, setPosition] = useState('bottom-right');
  const [primaryColor, setPrimaryColor] = useState('#0e2f44');
  const [textColor, setTextColor] = useState('#f2f2f2');
  const [originsText, setOriginsText] = useState('');
  const [expertPickerOpen, setExpertPickerOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const data = widgetQuery.data;
    if (!data) return;
    setExpertId(data.expert_id);
    setTitle(data.title || 'Geem');
    setSubtitle(data.subtitle || '');
    setGreeting(data.greeting || '');
    setLogoUrl(data.logo_url || '');
    setLocale(data.locale || 'ar');
    setPosition(data.position || 'bottom-right');
    setPrimaryColor(data.primary_color || '#0e2f44');
    setTextColor(data.text_color || '#f2f2f2');
    setOriginsText(originsToText(data.allowed_origins || []));
  }, [widgetQuery.data]);

  const expertList = expertsQuery.data ?? [];
  const selectedExpert = expertList.find((e) => e.id === expertId);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateChatWidget({
        expert_id: expertId,
        title,
        subtitle: subtitle || null,
        greeting: greeting || null,
        logo_url: logoUrl || null,
        locale,
        position,
        primary_color: primaryColor,
        text_color: textColor,
        allowed_origins: textToOrigins(originsText),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['chat-widget', workspaceId, app.slug], data);
      toast.success(t('apps.chatWidget.saved'));
    },
    onError: (err) => {
      const code = err instanceof ApiError ? err.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: disconnectChatWidget,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apps(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.appInstallations(workspaceId),
      });
      onOpenChange(false);
      toast.success(t('apps.toasts.uninstalled', { name: app.name }));
    },
    onError: (err) => {
      const code = err instanceof ApiError ? err.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    },
  });

  const embedHtml = useMemo(() => {
    const data: ChatWidgetInstance | undefined = widgetQuery.data;
    if (!data) return '';
    // Reflect latest locale in preview even before save.
    return data.embed_html.replace(
      /data-locale="[^"]*"/,
      `data-locale="${locale}"`,
    );
  }, [widgetQuery.data, locale]);

  async function copyEmbed() {
    if (!embedHtml) return;
    try {
      await navigator.clipboard.writeText(embedHtml);
      setCopied(true);
      toast.success(t('apps.chatWidget.copied'));
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error(t('apps.chatWidget.copyEmbed'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col"
        data-testid="chat-widget-config-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t('apps.chatWidget.title')}</DialogTitle>
          <DialogDescription>{t('apps.chatWidget.groundingHint')}</DialogDescription>
        </DialogHeader>

        <DialogBody className="overflow-y-auto space-y-6 py-2">
          {widgetQuery.isLoading ? (
            <div className="h-40 rounded-xl bg-muted animate-pulse" />
          ) : null}
          {widgetQuery.isError ? (
            <p className="text-sm text-destructive">
              {t(
                errorMessageKey(
                  widgetQuery.error instanceof ApiError
                    ? widgetQuery.error.code
                    : 'not_found',
                ),
              )}
            </p>
          ) : null}

          {widgetQuery.data ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="space-y-5">
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold">
                    {t('apps.chatWidget.grounding')}
                  </h3>
                  <button
                    type="button"
                    className={cn(
                      inputVariants({ variant: 'md' }),
                      'flex w-full items-center gap-2 text-start',
                      !canManage && 'pointer-events-none',
                    )}
                    onClick={() => setExpertPickerOpen(true)}
                    disabled={!canManage || expertsQuery.isLoading}
                    data-testid="chat-widget-expert-picker"
                  >
                    <Sparkles className="size-3.5 shrink-0 text-muted-foreground" />
                    <span
                      className={cn(
                        'min-w-0 flex-1 truncate',
                        !selectedExpert && 'text-muted-foreground',
                      )}
                    >
                      {selectedExpert?.name ?? t('apps.chatWidget.noExpert')}
                    </span>
                    <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                  </button>
                  {!expertId ? (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      {t('apps.chatWidget.needsExpert')}
                    </p>
                  ) : null}
                </section>

                <section className="space-y-3">
                  <h3 className="text-sm font-semibold">
                    {t('apps.chatWidget.appearance')}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="cw-title">{t('apps.chatWidget.fieldTitle')}</Label>
                      <Input
                        id="cw-title"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        disabled={!canManage}
                      />
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="cw-sub">{t('apps.chatWidget.fieldSubtitle')}</Label>
                      <Input
                        id="cw-sub"
                        value={subtitle}
                        onChange={(e) => setSubtitle(e.target.value)}
                        disabled={!canManage}
                      />
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="cw-greet">
                        {t('apps.chatWidget.fieldGreeting')}
                      </Label>
                      <Textarea
                        id="cw-greet"
                        value={greeting}
                        onChange={(e) => setGreeting(e.target.value)}
                        disabled={!canManage}
                        rows={2}
                      />
                    </div>
                    <div className="space-y-1.5 sm:col-span-2">
                      <Label htmlFor="cw-logo">{t('apps.chatWidget.fieldLogoUrl')}</Label>
                      <Input
                        id="cw-logo"
                        value={logoUrl}
                        placeholder="https://"
                        onChange={(e) => setLogoUrl(e.target.value)}
                        disabled={!canManage}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label>{t('apps.chatWidget.fieldLanguage')}</Label>
                      <Select
                        value={locale}
                        onValueChange={setLocale}
                        disabled={!canManage}
                      >
                        <SelectTrigger data-testid="chat-widget-locale">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="ar">{t('apps.chatWidget.langAr')}</SelectItem>
                          <SelectItem value="en">{t('apps.chatWidget.langEn')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>{t('apps.chatWidget.fieldPosition')}</Label>
                      <Select
                        value={position}
                        onValueChange={setPosition}
                        disabled={!canManage}
                      >
                        <SelectTrigger data-testid="chat-widget-position">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="bottom-right">
                            {t('apps.chatWidget.positionBottomRight')}
                          </SelectItem>
                          <SelectItem value="bottom-left">
                            {t('apps.chatWidget.positionBottomLeft')}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="cw-primary">
                        {t('apps.chatWidget.fieldPrimaryColor')}
                      </Label>
                      <div className="flex gap-2">
                        <Input
                          id="cw-primary"
                          value={primaryColor}
                          onChange={(e) => setPrimaryColor(e.target.value)}
                          disabled={!canManage}
                        />
                        <input
                          type="color"
                          aria-label={t('apps.chatWidget.fieldPrimaryColor')}
                          value={primaryColor.length === 7 ? primaryColor : '#0e2f44'}
                          onChange={(e) => setPrimaryColor(e.target.value)}
                          disabled={!canManage}
                          className="h-9 w-10 cursor-pointer rounded border border-border bg-transparent p-1"
                        />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="cw-text">{t('apps.chatWidget.fieldTextColor')}</Label>
                      <div className="flex gap-2">
                        <Input
                          id="cw-text"
                          value={textColor}
                          onChange={(e) => setTextColor(e.target.value)}
                          disabled={!canManage}
                        />
                        <input
                          type="color"
                          aria-label={t('apps.chatWidget.fieldTextColor')}
                          value={textColor.length === 7 ? textColor : '#f2f2f2'}
                          onChange={(e) => setTextColor(e.target.value)}
                          disabled={!canManage}
                          className="h-9 w-10 cursor-pointer rounded border border-border bg-transparent p-1"
                        />
                      </div>
                    </div>
                  </div>
                  {canManage ? (
                    <Button
                      type="button"
                      onClick={() => saveMutation.mutate()}
                      disabled={saveMutation.isPending}
                      data-testid="chat-widget-save"
                    >
                      {t('apps.chatWidget.save')}
                    </Button>
                  ) : null}
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">
                    {t('apps.chatWidget.allowedOrigins')}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {t('apps.chatWidget.allowedOriginsHint')}
                  </p>
                  <Textarea
                    value={originsText}
                    onChange={(e) => setOriginsText(e.target.value)}
                    placeholder={t('apps.chatWidget.allowedOriginsPlaceholder')}
                    disabled={!canManage}
                    rows={3}
                    data-testid="chat-widget-origins"
                  />
                </section>
              </div>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold">{t('apps.chatWidget.embedCode')}</h3>
                <p className="text-xs text-muted-foreground">
                  {t('apps.chatWidget.embedHint')}
                </p>
                <pre
                  className="rounded-xl border border-border bg-muted/40 p-3 text-xs overflow-x-auto whitespace-pre-wrap"
                  data-testid="chat-widget-embed"
                >
                  {embedHtml}
                </pre>
                <p className="text-xs text-muted-foreground">
                  {t('apps.chatWidget.embedNote')}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void copyEmbed()}
                  data-testid="chat-widget-copy-embed"
                >
                  <Copy className="size-3.5" />
                  {copied ? t('apps.chatWidget.copied') : t('apps.chatWidget.copyEmbed')}
                </Button>
              </section>
            </div>
          ) : null}
        </DialogBody>

        <DialogFooter className="gap-2 sm:justify-between">
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('apps.chatWidget.close')}
            </Button>
            {canManage ? (
              <Button
                type="button"
                variant="ghost"
                className="text-destructive"
                disabled={disconnectMutation.isPending}
                onClick={() => {
                  if (window.confirm(t('apps.chatWidget.disconnectConfirm'))) {
                    disconnectMutation.mutate();
                  }
                }}
                data-testid="chat-widget-disconnect"
              >
                {t('apps.chatWidget.disconnect')}
              </Button>
            ) : null}
          </div>
        </DialogFooter>

        <ExpertPickerDialog
          open={expertPickerOpen}
          onOpenChange={setExpertPickerOpen}
          experts={expertList}
          selectedId={expertId}
          onSelect={setExpertId}
          isLoading={expertsQuery.isLoading}
        />
      </DialogContent>
    </Dialog>
  );
}
