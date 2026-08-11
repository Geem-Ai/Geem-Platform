import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  extractHostWorkspaceSlug,
  isLocalDevEnvironment,
} from '@/features/workspaces/lib/hostname';
import { createWorkspace as apiCreateWorkspace } from '@/services/api';
import type { Membership, WorkspaceSummary } from '@/services/api/types';
import {
  clearWorkspaceContext,
  clearWorkspacePreference,
  loadWorkspacePreference,
  saveWorkspacePreference,
  setWorkspaceContext,
} from '@/services/auth/workspace-context';

type WorkspaceContextValue = {
  availableWorkspaces: WorkspaceSummary[];
  currentWorkspace: WorkspaceSummary | null;
  currentMembership: Membership | null;
  selectWorkspace: (workspaceId: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (input: { name: string; slug: string }) => Promise<WorkspaceSummary>;
  hostSlug: string | null;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function pickInitialWorkspace(
  workspaces: WorkspaceSummary[],
  userId: string,
  hostSlug: string | null,
  meCurrent: WorkspaceSummary | null,
): WorkspaceSummary | null {
  if (workspaces.length === 0) return null;

  if (hostSlug) {
    const fromHost = workspaces.find((w) => w.slug === hostSlug);
    if (fromHost) return fromHost;
  }

  if (meCurrent) {
    const match = workspaces.find((w) => w.id === meCurrent.id);
    if (match) return match;
  }

  const pref = loadWorkspacePreference(userId);
  if (pref) {
    const fromPref = workspaces.find((w) => w.id === pref);
    if (fromPref) return fromPref;
  }

  return workspaces[0] ?? null;
}

function syncClientHints(workspace: WorkspaceSummary | null) {
  if (!workspace) {
    clearWorkspaceContext();
    return;
  }
  setWorkspaceContext({
    workspaceId: workspace.id,
    workspaceSlug: isLocalDevEnvironment() ? workspace.slug : null,
  });
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { status, user, me, reloadMe } = useAuth();
  const queryClient = useQueryClient();
  const [availableWorkspaces, setAvailableWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<WorkspaceSummary | null>(null);
  const [currentMembership, setCurrentMembership] = useState<Membership | null>(null);

  const rootDomain = import.meta.env.VITE_ROOT_DOMAIN || 'localhost';
  const hostSlug =
    typeof window !== 'undefined'
      ? extractHostWorkspaceSlug(window.location.hostname, rootDomain)
      : null;

  useEffect(() => {
    if (status !== 'authenticated' || !user || !me) {
      if (status === 'unauthenticated') {
        setAvailableWorkspaces([]);
        setCurrentWorkspace(null);
        setCurrentMembership(null);
        clearWorkspaceContext();
      }
      return;
    }

    setAvailableWorkspaces(me.workspaces);
    const selected = pickInitialWorkspace(
      me.workspaces,
      user.id,
      hostSlug,
      me.current_workspace,
    );
    setCurrentWorkspace(selected);
    syncClientHints(selected);
    if (selected && me.membership && me.membership.workspace_id === selected.id) {
      setCurrentMembership(me.membership);
    } else if (selected) {
      setCurrentMembership({
        id: '',
        workspace_id: selected.id,
        user_id: user.id,
        role: selected.role,
        created_at: '',
      });
    } else {
      setCurrentMembership(null);
    }
    if (selected) {
      saveWorkspacePreference(user.id, selected.id);
    }
  }, [status, user, me, hostSlug]);

  const selectWorkspace = useCallback(
    (workspaceId: string) => {
      const next = availableWorkspaces.find((w) => w.id === workspaceId);
      if (!next || !user) return;

      const previousId = currentWorkspace?.id;
      if (previousId && previousId !== next.id) {
        void queryClient.cancelQueries({ queryKey: ['workspace', previousId] });
        void queryClient.removeQueries({ queryKey: ['workspace', previousId] });
      }

      setCurrentWorkspace(next);
      setCurrentMembership({
        id: currentMembership?.workspace_id === next.id ? currentMembership.id : '',
        workspace_id: next.id,
        user_id: user.id,
        role: next.role,
        created_at: currentMembership?.created_at ?? '',
      });
      syncClientHints(next);
      saveWorkspacePreference(user.id, next.id);
    },
    [availableWorkspaces, currentMembership, currentWorkspace?.id, queryClient, user],
  );

  const refreshWorkspaces = useCallback(async () => {
    const data = await reloadMe();
    setAvailableWorkspaces(data.workspaces);
  }, [reloadMe]);

  const createWorkspace = useCallback(
    async (input: { name: string; slug: string }) => {
      const created = await apiCreateWorkspace(input);
      const summary: WorkspaceSummary = {
        id: created.id,
        name: created.name,
        slug: created.slug,
        status: created.status,
        role: created.role ?? 'owner',
      };
      await refreshWorkspaces();
      selectWorkspace(summary.id);
      // Ensure selection even before me reload settles
      setCurrentWorkspace(summary);
      syncClientHints(summary);
      if (user) {
        saveWorkspacePreference(user.id, summary.id);
        setCurrentMembership({
          id: '',
          workspace_id: summary.id,
          user_id: user.id,
          role: 'owner',
          created_at: new Date().toISOString(),
        });
      }
      return summary;
    },
    [refreshWorkspaces, selectWorkspace, user],
  );

  useEffect(() => {
    return () => {
      if (status === 'unauthenticated' && user?.id) {
        clearWorkspacePreference(user.id);
      }
    };
  }, [status, user?.id]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      availableWorkspaces,
      currentWorkspace,
      currentMembership,
      selectWorkspace,
      refreshWorkspaces,
      createWorkspace,
      hostSlug,
    }),
    [
      availableWorkspaces,
      currentWorkspace,
      currentMembership,
      selectWorkspace,
      refreshWorkspaces,
      createWorkspace,
      hostSlug,
    ],
  );

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within WorkspaceProvider');
  }
  return ctx;
}
