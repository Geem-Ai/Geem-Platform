import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useIsMobile } from '@/hooks/use-mobile';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ScreenLoader } from '@/components/shared/ScreenLoader';

interface LayoutState {
  style: CSSProperties;
  bodyClassName: string;
  isMobile: boolean;
  isSidebarOpen: boolean;
  sidebarToggle: () => void;
}

const LayoutContext = createContext<LayoutState | undefined>(undefined);

interface LayoutProviderProps {
  children: ReactNode;
  style?: CSSProperties;
  bodyClassName?: string;
}

export function LayoutProvider({
  children,
  style: customStyle,
  bodyClassName = '',
}: LayoutProviderProps) {
  const isMobile = useIsMobile();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

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

    return () => {
      html.style.cssText = originalHtmlStyle;
      body.className = originalBodyClasses;
      body.removeAttribute('data-sidebar-open');
    };
  }, [cssVariables, bodyClassName, isSidebarOpen, isMobile]);

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
      }}
    >
      <div data-slot="layout-wrapper" className="flex grow">
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
