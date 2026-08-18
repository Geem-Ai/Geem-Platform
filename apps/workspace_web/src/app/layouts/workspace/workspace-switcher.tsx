import { useState } from 'react';
import { Building2, Check, ChevronDown, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { roleLabel } from '@/features/authz/role-summary';
import { CreateWorkspaceDialog } from '@/features/workspaces/components/CreateWorkspaceDialog';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export function WorkspaceSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { t } = useTranslation();
  const { availableWorkspaces, currentWorkspace, selectWorkspace } = useWorkspace();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <>
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
                  {currentWorkspace?.name ?? t('shell.workspacePlaceholder')}
                </span>
                <ChevronDown className="size-3.5 opacity-60" />
              </>
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent className="w-64" align="start" side="top">
          <DropdownMenuLabel>{t('shell.workspaces')}</DropdownMenuLabel>
          {availableWorkspaces.map((ws) => (
            <DropdownMenuItem
              key={ws.id}
              onClick={() => selectWorkspace(ws.id)}
              className="flex items-center justify-between gap-2"
            >
              <span className="truncate">
                {ws.name}
                <span className="ms-1 text-xs text-muted-foreground">
                  ({roleLabel(ws.role, t)})
                </span>
              </span>
              {currentWorkspace?.id === ws.id && <Check className="size-3.5 shrink-0" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => setCreateOpen(true)}
            data-testid="create-workspace-switcher-item"
          >
            <Plus className="size-3.5" />
            {t('shell.createWorkspace')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />
    </>
  );
}
