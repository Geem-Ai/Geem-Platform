import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useLocation } from 'react-router-dom';
import { useIsMobile } from '@/hooks/use-mobile';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

export type SidebarMode = 'chat' | 'workspace';

interface LayoutState {
  style: CSSProperties;
  bodyClassName: string;
  isMobile: boolean;
  isSidebarOpen: boolean;
  sidebarToggle: () => void;
  sidebarMode: SidebarMode;
  setSidebarMode: (mode: SidebarMode) => void;
  showFavoritesOnly: boolean;
  setShowFavoritesOnly: (value: boolean | ((prev: boolean) => boolean)) => void;
}

const LayoutContext = createContext<LayoutState | undefined>(undefined);

interface LayoutProviderProps {
  children: ReactNode;
  style?: CSSProperties;
  bodyClassName?: string;
}

function isChatPath(pathname: string): boolean {
  return pathname === '/chat' || pathname.startsWith('/chat/');
}

export function LayoutProvider({
  children,
  style: customStyle,
  bodyClassName = '',
}: LayoutProviderProps) {
  const isMobile = useIsMobile();
  const { pathname } = useLocation();
  const chatRoute = isChatPath(pathname);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [manualMode, setManualMode] = useState<SidebarMode | null>(null);
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);

  // Crossing chat ↔ non-chat routes, or navigating between chat pages
  // (e.g. /chat → /chat/:id), clears manual override so settings mode
  // does not stick across a new conversation.
  useEffect(() => {
    setManualMode(null);
    setShowFavoritesOnly(false);
  }, [pathname]);

  const sidebarMode: SidebarMode = manualMode ?? (chatRoute ? 'chat' : 'workspace');

  const setSidebarMode = (mode: SidebarMode) => {
    setManualMode(mode);
  };

  const cssVariables = useMemo(
    () =>
      ({
        '--sidebar-width': '255px',
        '--sidebar-width-collapsed': '60px',
        '--sidebar-width-mobile': '60px',
        '--header-height': '60px',
        '--header-height-mobile': '60px',
        ...(customStyle || {}),
      }) as CSSProperties,
    [customStyle],
  );

  const style: CSSProperties = useMemo(() => ({ ...cssVariables }), [cssVariables]);

  const sidebarToggle = () => setIsSidebarOpen((open) => !open);

  useEffect(() => {
    if (isMobile === undefined) return;

    const html = document.documentElement;
    const body = document.body;

    const originalHtmlStyle = html.style.cssText;
    const originalBodyClasses = body.className;

    Object.entries(cssVariables).forEach(([prop, val]) => {
      html.style.setProperty(prop, String(val));
    });

    if (bodyClassName) {
      body.className = `${originalBodyClasses} ${bodyClassName}`.trim();
    }

    body.setAttribute('data-sidebar-open', isSidebarOpen.toString());
    body.setAttribute('data-sidebar-mode', sidebarMode);

    return () => {
      html.style.cssText = originalHtmlStyle;
      body.className = originalBodyClasses;
      body.removeAttribute('data-sidebar-open');
      body.removeAttribute('data-sidebar-mode');
    };
  }, [cssVariables, bodyClassName, isSidebarOpen, isMobile, sidebarMode]);

  if (isMobile === undefined) {
    return <ScreenLoader />;
  }

  return (
    <LayoutContext.Provider
      value={{
        bodyClassName,
        style,
        isMobile,
        isSidebarOpen,
        sidebarToggle,
        sidebarMode,
        setSidebarMode,
        showFavoritesOnly,
        setShowFavoritesOnly,
      }}
    >
      <div data-slot="layout-wrapper" className="flex grow min-w-0 w-full">
        <TooltipProvider delayDuration={0}>{children}</TooltipProvider>
      </div>
    </LayoutContext.Provider>
  );
}

export const useLayout = () => {
  const context = useContext(LayoutContext);
  if (!context) {
    throw new Error('useLayout must be used within a LayoutProvider');
  }
  return context;
};
