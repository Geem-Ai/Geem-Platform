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
  fetchPlatformMe,
  loginAccount,
  logoutAllSessions,
  logoutSession,
  refreshSession,
  type PlatformMeResponse,
  type User,
} from '@/services/api';
import { ApiError } from '@/services/api/errors';
import {
  clearAuthSession,
  getAuthSession,
  setAuthSession,
} from '@/services/auth/session';

export type AuthStatus = 'bootstrapping' | 'authenticated' | 'unauthenticated';

export class PlatformAccessDeniedError extends Error {
  constructor() {
    super('Platform Admin access required');
    this.name = 'PlatformAccessDeniedError';
  }
}

type AuthContextValue = {
  status: AuthStatus;
  user: User | null;
  accessToken: string | null;
  me: PlatformMeResponse | null;
  login: (email: string, password: string) => Promise<PlatformMeResponse>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
  accessDenied: boolean;
  clearAccessDenied: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function applyToken(accessToken: string, userId: string) {
  setAuthSession({ accessToken, userId });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>('bootstrapping');
  const [user, setUser] = useState<User | null>(null);
  const [me, setMe] = useState<PlatformMeResponse | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const bootstrapped = useRef(false);

  const clearLocalState = useCallback(() => {
    clearAuthSession();
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
    return res.access_token;
  }, []);

  useEffect(() => {
    configureApiClient({
      baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
      getAccessToken: () => getAuthSession().accessToken,
      refreshAccessToken: doRefresh,
      onSessionInvalid: handleSessionInvalid,
    });
  }, [doRefresh, handleSessionInvalid]);

  const revokeAndDeny = useCallback(async () => {
    try {
      await logoutSession();
    } catch {
      // still clear locally
    }
    clearLocalState();
    setAccessDenied(true);
  }, [clearLocalState]);

  const loadPlatformMe = useCallback(async (): Promise<PlatformMeResponse> => {
    try {
      const data = await fetchPlatformMe();
      setMe(data);
      setUser(data.user);
      setStatus('authenticated');
      setAccessDenied(false);
      return data;
    } catch (err) {
      if (err instanceof ApiError && err.code === 'platform_admin_required') {
        await revokeAndDeny();
        throw new PlatformAccessDeniedError();
      }
      throw err;
    }
  }, [revokeAndDeny]);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    void (async () => {
      try {
        const tokenRes = await refreshSession();
        applyToken(tokenRes.access_token, tokenRes.user.id);
        setAccessToken(tokenRes.access_token);
        setUser(tokenRes.user);
        await loadPlatformMe();
      } catch (err) {
        if (err instanceof PlatformAccessDeniedError) {
          return;
        }
        clearAuthSession();
        setStatus('unauthenticated');
      }
    })();
  }, [loadPlatformMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await loginAccount(email, password);
      applyToken(res.access_token, res.user.id);
      setAccessToken(res.access_token);
      setUser(res.user);
      setSessionExpired(false);
      return loadPlatformMe();
    },
    [loadPlatformMe],
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
      logout,
      logoutAll,
      sessionExpired,
      clearSessionExpired: () => setSessionExpired(false),
      accessDenied,
      clearAccessDenied: () => setAccessDenied(false),
    }),
    [
      status,
      user,
      accessToken,
      me,
      login,
      logout,
      logoutAll,
      sessionExpired,
      accessDenied,
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
