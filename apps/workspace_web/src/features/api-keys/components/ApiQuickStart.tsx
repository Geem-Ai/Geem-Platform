import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
  floatingSheetPanel,
} from '@/components/ui/sheet';
import { getApiBaseUrl } from '@/services/api/client';
import { publicChatCurlExample, publicChatStreamBodyExample } from '../lib/quick-start';
import { CopyableCodeBlock } from './CopyableCodeBlock';

const SHEET_PANEL = floatingSheetPanel(
  'sm:w-[min(100%-2.5rem,42rem)]',
  'lg:w-[42rem]',
);

type ApiQuickStartProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function ApiQuickStart({ open, onOpenChange }: ApiQuickStartProps) {
  const { t } = useTranslation();
  const example = publicChatCurlExample(getApiBaseUrl());
  const streamBody = publicChatStreamBodyExample();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
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
              <CopyableCodeBlock code={example} testId="api-quick-start-curl" />
              <div className="space-y-2 min-w-0">
                <p className="text-sm font-medium">{t('apiKeys.streamTitle')}</p>
                <p className="text-sm text-muted-foreground text-pretty break-words">
                  {t('apiKeys.streamHint')}
                </p>
                <CopyableCodeBlock
                  code={streamBody}
                  testId="api-quick-start-stream"
                />
              </div>
            </div>
          </ScrollArea>
        </SheetBody>
        <SheetFooter className="flex-row border-t justify-end items-center p-5 border-border gap-2 sm:space-x-0">
          <Button type="button" size="sm" variant="outline" asChild>
            <Link to="/experts" onClick={() => onOpenChange(false)}>
              {t('apiKeys.findExpertId')}
            </Link>
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
