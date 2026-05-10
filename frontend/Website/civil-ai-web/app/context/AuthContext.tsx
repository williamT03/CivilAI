"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { AUTH_API_BASE } from "../lib/apiConfig";

const ACCESS_TOKEN_KEY = "civilai_access_token";
const REFRESH_TOKEN_KEY = "civilai_refresh_token";
const GUEST_SESSION_KEY = "civilai_guest_session";

export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string | null;
  jurisdiction?: string | null;
  is_active: boolean;
  is_admin: boolean;
  is_guest?: boolean;
  created_at?: string;
  last_login?: string | null;
}

export interface RegisterPayload {
  email: string;
  username: string;
  password: string;
  full_name?: string;
  jurisdiction?: string;
}

export interface UpdateProfilePayload {
  full_name?: string;
  jurisdiction?: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isGuest: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  continueAsGuest: (payload?: UpdateProfilePayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
  updateProfile: (payload: UpdateProfilePayload) => Promise<User>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readStoredValue(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(key);
}

function writeStoredValue(key: string, value: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (value === null) {
    window.localStorage.removeItem(key);
    return;
  }

  window.localStorage.setItem(key, value);
}

function readStoredGuestUser(): User | null {
  const rawValue = readStoredValue(GUEST_SESSION_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as User;
    if (parsed && parsed.is_guest) {
      return parsed;
    }
  } catch {
    return null;
  }

  return null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : typeof payload === "string"
          ? payload
          : "Request failed.";
    throw new Error(detail);
  }

  return payload as T;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const persistTokens = useCallback((nextAccessToken: string | null, nextRefreshToken: string | null) => {
    setToken(nextAccessToken);
    setRefreshToken(nextRefreshToken);
    writeStoredValue(ACCESS_TOKEN_KEY, nextAccessToken);
    writeStoredValue(REFRESH_TOKEN_KEY, nextRefreshToken);
    if (nextAccessToken) {
      writeStoredValue(GUEST_SESSION_KEY, null);
    }
  }, []);

  const persistGuestUser = useCallback((nextGuestUser: User | null) => {
    if (nextGuestUser) {
      setUser(nextGuestUser);
      writeStoredValue(GUEST_SESSION_KEY, JSON.stringify(nextGuestUser));
    } else {
      writeStoredValue(GUEST_SESSION_KEY, null);
    }
  }, []);

  const clearSession = useCallback(() => {
    setUser(null);
    persistTokens(null, null);
    persistGuestUser(null);
  }, [persistGuestUser, persistTokens]);

  const refreshAccessToken = useCallback(async (currentRefreshToken: string): Promise<TokenResponse> => {
    const response = await fetch(
      `${AUTH_API_BASE}/refresh?refresh_token=${encodeURIComponent(currentRefreshToken)}`,
      {
        method: "POST",
      },
    );
    const tokens = await parseResponse<TokenResponse>(response);
    persistTokens(tokens.access_token, tokens.refresh_token);
    return tokens;
  }, [persistTokens]);

  const fetchCurrentUser = useCallback(async function loadCurrentUser(
    accessToken: string,
    currentRefreshToken: string | null,
  ): Promise<User | null> {
    const response = await fetch(`${AUTH_API_BASE}/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (response.status === 401 && currentRefreshToken) {
      const refreshed = await refreshAccessToken(currentRefreshToken);
      return loadCurrentUser(refreshed.access_token, refreshed.refresh_token);
    }

    const nextUser = await parseResponse<User>(response);
    setUser(nextUser);
    return nextUser;
  }, [refreshAccessToken]);

  async function refreshUser(): Promise<User | null> {
    if (user?.is_guest) {
      return user;
    }

    const currentToken = token ?? readStoredValue(ACCESS_TOKEN_KEY);
    const currentRefreshToken = refreshToken ?? readStoredValue(REFRESH_TOKEN_KEY);

    if (!currentToken) {
      setUser(null);
      return null;
    }

    try {
      return await fetchCurrentUser(currentToken, currentRefreshToken);
    } catch {
      clearSession();
      return null;
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function bootstrapSession() {
      const storedToken = readStoredValue(ACCESS_TOKEN_KEY);
      const storedRefreshToken = readStoredValue(REFRESH_TOKEN_KEY);

      if (!storedToken) {
        const storedGuestUser = readStoredGuestUser();
        if (storedGuestUser && isMounted) {
          setUser(storedGuestUser);
          setIsLoading(false);
          return;
        }
        if (isMounted) {
          setIsLoading(false);
        }
        return;
      }

      setToken(storedToken);
      setRefreshToken(storedRefreshToken);

      try {
        await fetchCurrentUser(storedToken, storedRefreshToken);
      } catch {
        clearSession();
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void bootstrapSession();

    return () => {
      isMounted = false;
    };
  }, [clearSession, fetchCurrentUser]);

  async function login(username: string, password: string): Promise<void> {
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);

    const response = await fetch(`${AUTH_API_BASE}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });

    const tokens = await parseResponse<TokenResponse>(response);
    persistTokens(tokens.access_token, tokens.refresh_token);
    persistGuestUser(null);
    await fetchCurrentUser(tokens.access_token, tokens.refresh_token);
  }

  async function register(payload: RegisterPayload): Promise<void> {
    const response = await fetch(`${AUTH_API_BASE}/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    await parseResponse<User>(response);
    await login(payload.username, payload.password);
  }

  async function continueAsGuest(payload?: UpdateProfilePayload): Promise<void> {
    const guestUser: User = {
      id: 0,
      email: "",
      username: "guest",
      full_name: payload?.full_name?.trim() || "Guest User",
      jurisdiction: payload?.jurisdiction?.trim() || null,
      is_active: true,
      is_admin: false,
      is_guest: true,
      created_at: new Date().toISOString(),
      last_login: null,
    };

    persistTokens(null, null);
    persistGuestUser(guestUser);
  }

  async function logout(): Promise<void> {
    if (user?.is_guest) {
      clearSession();
      return;
    }

    const currentRefreshToken = refreshToken ?? readStoredValue(REFRESH_TOKEN_KEY);

    try {
      if (currentRefreshToken) {
        await fetch(
          `${AUTH_API_BASE}/logout?refresh_token=${encodeURIComponent(currentRefreshToken)}`,
          {
            method: "POST",
          },
        );
      }
    } catch {
      // Best-effort logout is fine here because local cleanup is the important part.
    } finally {
      clearSession();
    }
  }

  async function updateProfile(payload: UpdateProfilePayload): Promise<User> {
    if (user?.is_guest) {
      const updatedGuestUser: User = {
        ...user,
        full_name: payload.full_name !== undefined ? payload.full_name || "Guest User" : user.full_name,
        jurisdiction: payload.jurisdiction !== undefined ? payload.jurisdiction || null : user.jurisdiction,
        is_guest: true,
      };
      setUser(updatedGuestUser);
      persistGuestUser(updatedGuestUser);
      return updatedGuestUser;
    }

    let activeToken = token ?? readStoredValue(ACCESS_TOKEN_KEY);
    const activeRefreshToken = refreshToken ?? readStoredValue(REFRESH_TOKEN_KEY);

    if (!activeToken) {
      throw new Error("You need to sign in again before updating your account.");
    }

    let response = await fetch(`${AUTH_API_BASE}/me`, {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${activeToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (response.status === 401 && activeRefreshToken) {
      const refreshed = await refreshAccessToken(activeRefreshToken);
      activeToken = refreshed.access_token;
      response = await fetch(`${AUTH_API_BASE}/me`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${activeToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
    }

    const updatedUser = await parseResponse<User>(response);
    setUser(updatedUser);
    return updatedUser;
  }

  const value: AuthContextValue = {
    user,
    token,
    refreshToken,
    isAuthenticated: Boolean(user && (token || user.is_guest)),
    isGuest: Boolean(user?.is_guest),
    isLoading,
    login,
    register,
    continueAsGuest,
    logout,
    refreshUser,
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return context;
}
