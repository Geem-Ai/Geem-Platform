import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MessageSquarePlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface NewChatButtonProps {
  collapsed?: boolean;
  className?: string;
}

export function NewChatButton({ collapsed, className }: NewChatButtonProps) {
  const { t, i18n } = useTranslation();
  const label = t('chat.newChat');
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';

  const button = (
    <Button
      asChild
      className={cn(
        'new-chat-gradient w-full max-w-full min-w-0 h-10 rounded-full gap-2 text-primary-foreground',
        'border-0 hover:brightness-110 overflow-hidden',
        collapsed && 'size-10 p-0',
        className,
      )}
      data-testid="new-chat-button"
    >
      <Link to="/chat" aria-label={label} className="min-w-0">
        <MessageSquarePlus className="size-4 shrink-0" />
        {!collapsed && <span className="truncate font-semibold">{label}</span>}
      </Link>
    </Button>
  );

  if (!collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}
