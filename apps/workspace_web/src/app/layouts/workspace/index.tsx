import type { CSSProperties } from 'react';
import { LayoutProvider } from './context';
import { Wrapper } from './wrapper';

export function WorkspaceLayout() {
  return (
    <LayoutProvider
      bodyClassName="bg-muted"
      style={
        {
          '--sidebar-width': '255px',
          '--sidebar-header-height': '60px',
          '--header-height': '60px',
          '--header-height-mobile': '60px',
        } as CSSProperties
      }
    >
      <Wrapper />
    </LayoutProvider>
  );
}
