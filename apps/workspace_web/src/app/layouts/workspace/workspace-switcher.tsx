import { Building2, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export function WorkspaceSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className={cn(
            'w-full justify-start gap-2.5 px-2.5',
            collapsed && 'justify-center px-0',
          )}
        >
          <Building2 className="size-4 shrink-0" />
          {!collapsed && (
            <>
              <span className="truncate flex-1 text-start">
                {t('shell.workspacePlaceholder')}
              </span>
              <ChevronDown className="size-3.5 opacity-60" />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="top">
        <DropdownMenuLabel>{t('shell.workspacePlaceholder')}</DropdownMenuLabel>
        <DropdownMenuItem disabled>{t('shell.workspaceSwitcherHint')}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
