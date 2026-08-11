import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Direction } from 'radix-ui';

/**
 * Keeps Radix primitives (ScrollArea, menus, etc.) in sync with document dir.
 * Without this, ScrollArea defaults to dir="ltr" and breaks RTL flex/nav.
 */
export function DirectionProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const [dir, setDir] = useState<'ltr' | 'rtl'>(() =>
    i18n.language === 'ar' ? 'rtl' : 'ltr',
  );

  useEffect(() => {
    const next = i18n.language === 'ar' ? 'rtl' : 'ltr';
    setDir(next);
  }, [i18n.language]);

  return (
    <Direction.DirectionProvider dir={dir}>{children}</Direction.DirectionProvider>
  );
}
