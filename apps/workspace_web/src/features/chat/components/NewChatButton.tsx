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
        'w-full h-10 rounded-full shadow-md gap-2',
        collapsed && 'size-10 p-0',
        className,
      )}
      data-testid="new-chat-button"
    >
      <Link to="/chat" aria-label={label}>
        <MessageSquarePlus className="size-4 shrink-0" />
        {!collapsed && <span className="truncate">{label}</span>}
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
