import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  configureApiClient,
  fetchMe,
  loginAccount,
  logoutAllSessions,
  logoutSession,
  refreshSession,
  registerAccount,
  type MeResponse,
  type User,
} from '@/services/api';
import {
  clearAuthSession,
  getAuthSession,
  setAuthSession,
} from '@/services/auth/session';
import {
  clearWorkspaceContext,
  getWorkspaceContext,
} from '@/services/auth/workspace-context';

export type AuthStatus = 'bootstrapping' | 'authenticated' | 'unauthenticated';

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  accessToken: string | null;
  me: MeResponse | null;
  login: (email: string, password: string) => Promise<MeResponse>;
  register: (email: string, password: string) => Promise<MeResponse>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshSession: () => Promise<string>;
  reloadMe: () => Promise<MeResponse>;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function applyToken(accessToken: string, userId: string) {
  setAuthSession({ accessToken, userId });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>('bootstrapping');
  const [user, setUser] = useState<User | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const bootstrapped = useRef(false);

  const clearLocalState = useCallback(() => {
    clearAuthSession();
    clearWorkspaceContext();
    setUser(null);
    setMe(null);
    setAccessToken(null);
    setStatus('unauthenticated');
    void queryClient.clear();
  }, [queryClient]);

  const handleSessionInvalid = useCallback(() => {
    setSessionExpired(true);
    clearLocalState();
  }, [clearLocalState]);

  const doRefresh = useCallback(async (): Promise<string> => {
    const res = await refreshSession();
    applyToken(res.access_token, res.user.id);
    setAccessToken(res.access_token);
    setUser(res.user);
    setStatus('authenticated');
    return res.access_token;
  }, []);

  useEffect(() => {
    configureApiClient({
      baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
      getAccessToken: () => getAuthSession().accessToken,
      getWorkspaceId: () => getWorkspaceContext().workspaceId,
      getWorkspaceSlug: () => getWorkspaceContext().workspaceSlug,
      refreshAccessToken: doRefresh,
      onSessionInvalid: handleSessionInvalid,
    });
  }, [doRefresh, handleSessionInvalid]);

  const reloadMe = useCallback(async (): Promise<MeResponse> => {
    const data = await fetchMe();
    setMe(data);
    setUser(data.user);
    setStatus('authenticated');
    return data;
  }, []);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    void (async () => {
      try {
        // Cookie-based bootstrap: refresh → me
        const tokenRes = await refreshSession();
        applyToken(tokenRes.access_token, tokenRes.user.id);
        setAccessToken(tokenRes.access_token);
        setUser(tokenRes.user);
        const data = await fetchMe();
        setMe(data);
        setUser(data.user);
        setStatus('authenticated');
      } catch {
        clearAuthSession();
        setStatus('unauthenticated');
      }
    })();
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await loginAccount(email, password);
      applyToken(res.access_token, res.user.id);
      setAccessToken(res.access_token);
      setUser(res.user);
      setSessionExpired(false);
      const data = await fetchMe();
      setMe(data);
      setStatus('authenticated');
      return data;
    },
    [],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      const res = await registerAccount(email, password);
      applyToken(res.access_token, res.user.id);
      setAccessToken(res.access_token);
      setUser(res.user);
      setSessionExpired(false);
      const data = await fetchMe();
      setMe(data);
      setStatus('authenticated');
      return data;
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } catch {
      // still clear locally
    }
    clearLocalState();
  }, [clearLocalState]);

  const logoutAll = useCallback(async () => {
    try {
      await logoutAllSessions();
    } catch {
      // still clear locally
    }
    clearLocalState();
  }, [clearLocalState]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      accessToken,
      me,
      login,
      register,
      logout,
      logoutAll,
      refreshSession: doRefresh,
      reloadMe,
      sessionExpired,
      clearSessionExpired: () => setSessionExpired(false),
    }),
    [
      status,
      user,
      accessToken,
      me,
      login,
      register,
      logout,
      logoutAll,
      doRefresh,
      reloadMe,
      sessionExpired,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
