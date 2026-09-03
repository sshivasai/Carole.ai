"use client";
import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { api } from "./useApi";

interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, firstName?: string, lastName?: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const setAuth = useCallback((u: User, t: string) => {
    localStorage.setItem("carole_token", t);
    localStorage.setItem("carole_user", JSON.stringify(u));
    localStorage.setItem("carole_sidebar_collapsed", "true");
    setUser(u);
    setToken(t);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("carole_token");
    localStorage.removeItem("carole_user");
    try {
      Object.keys(localStorage).forEach(k => {
        if (k.startsWith("carole_pending_approvals_")) {
          localStorage.removeItem(k);
        }
      });
    } catch {}
    setUser(null);
    setToken(null);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.getMe();
      setUser(me);
    } catch {
      logout();
    }
  }, [logout]);

  // Bootstrap from localStorage on mount
  useEffect(() => {
    async function bootstrap() {
      const storedToken = localStorage.getItem("carole_token");
      const storedUser = localStorage.getItem("carole_user");
      if (storedToken && storedUser) {
        try {
          const me = await api.getMe();
          setToken(storedToken);
          setUser(me);
        } catch {
          logout();
        }
      }
      setLoading(false);
    }
    bootstrap();
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setAuth(res.user, res.token);
  }, [setAuth]);

  const signup = useCallback(async (email: string, password: string, firstName?: string, lastName?: string) => {
    const res = await api.signup(email, password, firstName, lastName);
    setAuth(res.user, res.token);
  }, [setAuth]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
