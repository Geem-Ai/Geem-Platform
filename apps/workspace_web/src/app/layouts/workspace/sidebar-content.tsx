import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  ConversationListsShimmer,
  FavoriteConversations,
  FavoriteConversationsShimmer,
  PinnedConversations,
  RecentConversations,
} from '@/features/chat/components/ConversationLists';
import { NewChatButton } from '@/features/chat/components/NewChatButton';
import { QuickActions } from '@/features/chat/components/QuickActions';
import { useConversations } from '@/features/chat/hooks/useConversations';
import { useLayout } from './context';
import { workspaceNav, type NavItem } from './nav-config';

const navItemClass = (
  collapsed: boolean,
  nested: boolean,
  active = false,
) =>
  cn(
    'flex w-full min-w-0 items-center justify-start gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
    nested && 'ps-4',
    active
      ? 'bg-accent text-accent-foreground font-medium'
      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
    collapsed && 'justify-center px-0',
  );

/** Group label — no href. When collapsed, click expands the sidebar. */
function NavGroupItem({
  item,
  collapsed,
}: {
  item: NavItem;
  collapsed: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { sidebarToggle } = useLayout();
  const label = t(item.labelKey);
  const Icon = item.icon;
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';

  if (!collapsed) {
    return (
      <div
        className={cn(
          navItemClass(false, false),
          'pointer-events-none hover:bg-transparent hover:text-muted-foreground',
        )}
        data-testid={`nav-group-${item.id}`}
      >
        <Icon className="size-4 shrink-0" />
        <span className="min-w-0 truncate">{label}</span>
      </div>
    );
  }

  const content = (
    <button
      type="button"
      className={navItemClass(true, false)}
      onClick={() => sidebarToggle()}
      aria-label={label}
      data-testid={`nav-group-${item.id}`}
    >
      <Icon className="size-4 shrink-0" />
    </button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}

function NavLinkItem({
  item,
  collapsed,
  nested = false,
}: {
  item: NavItem;
  collapsed: boolean;
  nested?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const label = t(item.labelKey);
  const Icon = item.icon;
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';

  if (!item.to) {
    return null;
  }

  const link = (
    <NavLink
      to={item.to}
      // Nested leaves must match exactly. Prefix match would paint every
      // /billing/* child as active under a shared prefix.
      end={nested}
      className={({ isActive }) => navItemClass(collapsed, nested, isActive)}
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span className="min-w-0 truncate">{label}</span>}
    </NavLink>
  );

  if (!collapsed) {
    return link;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}

function WorkspaceNav({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();

  return (
    <nav
      className="w-full p-2.5 space-y-1"
      aria-label={t('shell.workspaceSettings')}
      data-testid="workspace-nav"
    >
      {workspaceNav.map((item) => {
        const isGroup = Boolean(item.children?.length);

        return (
          <div key={item.id} className="w-full space-y-1">
            {isGroup ? (
              <NavGroupItem item={item} collapsed={collapsed} />
            ) : (
              <NavLinkItem item={item} collapsed={collapsed} />
            )}
            {!collapsed &&
              item.children?.map((child) => (
                <NavLinkItem
                  key={child.id}
                  item={child}
                  collapsed={collapsed}
                  nested
                />
              ))}
            {!collapsed && isGroup && (
              <Separator className="my-2 opacity-80" />
            )}
          </div>
        );
      })}
    </nav>
  );
}

function BackToChats({ collapsed }: { collapsed: boolean }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { setSidebarMode } = useLayout();
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';
  const label = t('shell.backToChats');
  const onChatRoute = pathname === '/chat' || pathname.startsWith('/chat/');

  function handleClick() {
    setSidebarMode('chat');
    // Only leave the current page when we are outside Chat.
    if (!onChatRoute) {
      void navigate('/chat');
    }
  }

  const button = (
    <Button
      type="button"
      variant="ghost"
      className={cn(
        'w-full justify-start gap-2.5 px-2.5 text-sm',
        collapsed && 'justify-center px-0 size-10',
      )}
      onClick={handleClick}
      data-testid="back-to-chats"
      aria-label={label}
    >
      <ArrowLeft
        className={cn('size-4 shrink-0', i18n.language === 'ar' && 'rotate-180')}
      />
      {!collapsed && <span className="truncate">{label}</span>}
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

function ChatHistorySections({ collapsed }: { collapsed: boolean }) {
  const conversationsQuery = useConversations();
  const conversations = conversationsQuery.data ?? [];
  const { showFavoritesOnly } = useLayout();

  if (collapsed) {
    return (
      <div className="px-2 pb-2 space-y-2 flex flex-col items-center">
        <NewChatButton collapsed />
        <QuickActions collapsed />
      </div>
    );
  }

  return (
    <div className="min-w-0 max-w-full space-y-3.5 pb-2" data-testid="chat-sidebar-history">
      <div className="min-w-0 px-2.5">
        <NewChatButton />
      </div>

      <Separator className="mx-2.5 opacity-80" />

      {conversationsQuery.isLoading ? (
        showFavoritesOnly ? (
          <FavoriteConversationsShimmer />
        ) : (
          <ConversationListsShimmer />
        )
      ) : showFavoritesOnly ? (
        <FavoriteConversations conversations={conversations} />
      ) : (
        <>
          <PinnedConversations conversations={conversations} />
          <Separator className="mx-2.5 opacity-80" />
          <RecentConversations conversations={conversations} />
        </>
      )}

      <Separator className="mx-2.5 opacity-80" />

      <div className="min-w-0 px-2.5">
        <QuickActions />
      </div>
    </div>
  );
}

export function SidebarContent() {
  const { i18n } = useTranslation();
  const { isSidebarOpen, sidebarMode } = useLayout();
  const collapsed = !isSidebarOpen;
  const dir = i18n.language === 'ar' ? 'rtl' : 'ltr';

  return (
    <div
      dir={dir}
      className="min-h-0 min-w-0 flex-1 w-full overflow-y-auto overflow-x-hidden"
    >
      <div
        className="flex flex-col gap-1 py-2 min-w-0 w-full max-w-full"
        data-testid={`sidebar-mode-${sidebarMode}`}
      >
        {sidebarMode === 'chat' ? (
          <ChatHistorySections collapsed={collapsed} />
        ) : (
          <div className="space-y-1 min-w-0 w-full">
            <div className="px-2.5 pb-1">
              <BackToChats collapsed={collapsed} />
            </div>
            <Separator className="mx-2.5 my-1 opacity-80" />
            <WorkspaceNav collapsed={collapsed} />
          </div>
        )}
      </div>
    </div>
  );
}
