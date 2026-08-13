import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { getApiBaseUrl } from '@/services/api/client';
import { copyText } from '@/lib/clipboard';
import { publicChatCurlExample, publicChatStreamBodyExample } from '../lib/quick-start';

/** Metronic-style floating inset panel — same as Expert sheets. */
const SHEET_PANEL =
  'gap-0 w-full min-w-0 overflow-hidden sm:max-w-none sm:w-[min(100%-2.5rem,42rem)] lg:w-[42rem] inset-5 border start-auto h-auto rounded-lg p-0 [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5';

type ApiQuickStartProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ApiQuickStart({ open, onOpenChange }: ApiQuickStartProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const example = publicChatCurlExample(getApiBaseUrl());
  const streamBody = publicChatStreamBodyExample();

  async function handleCopy() {
    const ok = await copyText(example);
    if (ok) {
      setCopied(true);
      toast.success(t('apiKeys.copied'));
    } else {
      toast.error(t('apiKeys.copyFailed'));
    }
  }

  function handleOpenChange(next: boolean) {
    if (!next) setCopied(false);
    onOpenChange(next);
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent side="end" className={SHEET_PANEL} data-testid="api-quick-start">
        <SheetHeader className="border-b py-3.5 px-5 border-border text-start min-w-0">
          <div className="space-y-1 pe-8 min-w-0">
            <SheetTitle className="font-medium">{t('apiKeys.quickStartTitle')}</SheetTitle>
            <SheetDescription className="text-pretty break-words">
              {t('apiKeys.quickStartHint')}
            </SheetDescription>
          </div>
        </SheetHeader>
        <SheetBody className="p-0 grow min-h-0 min-w-0 overflow-hidden">
          <ScrollArea
            className="h-[calc(100dvh-12rem)] min-w-0"
            viewportClassName="min-w-0 [&>div]:!block [&>div]:min-w-0 [&>div]:max-w-full"
          >
            <div className="space-y-5 p-5 min-w-0 max-w-full">
              <pre
                dir="ltr"
                className="max-w-full overflow-x-auto rounded-md border border-border bg-muted/40 p-3 text-xs font-mono whitespace-pre-wrap break-all"
                data-testid="api-quick-start-curl"
              >
                {example}
              </pre>
              <div className="space-y-2 min-w-0">
                <p className="text-sm font-medium">{t('apiKeys.streamTitle')}</p>
                <p className="text-sm text-muted-foreground text-pretty break-words">
                  {t('apiKeys.streamHint')}
                </p>
                <pre
                  dir="ltr"
                  className="max-w-full overflow-x-auto rounded-md border border-border bg-muted/40 p-3 text-xs font-mono whitespace-pre-wrap break-all"
                  data-testid="api-quick-start-stream"
                >
                  {streamBody}
                </pre>
              </div>
            </div>
          </ScrollArea>
        </SheetBody>
        <SheetFooter className="flex-row border-t justify-end items-center p-5 border-border gap-2 sm:space-x-0">
          <Button type="button" size="sm" variant="outline" asChild>
            <Link to="/experts" onClick={() => handleOpenChange(false)}>
              {t('apiKeys.findExpertId')}
            </Link>
          </Button>
          <Button type="button" size="sm" onClick={() => void handleCopy()}>
            {copied ? t('apiKeys.copied') : t('apiKeys.copySnippet')}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
