import React, { createContext, useContext, useEffect, useState } from "react";

import { createAsyncStorageAdapter } from "@/storage/storage";

type AuthStatus = "loading" | "guest" | "onboarding";

interface AuthContextValue {
  status: AuthStatus;
  enterAsGuest: () => Promise<void>;
  resetOnboarding: () => Promise<void>;
}

const guestKey = "aurion-guest-v1";
const storage = createAsyncStorageAdapter();
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let mounted = true;
    storage
      .getItem(guestKey)
      .then((value) => {
        if (!mounted) {
          return;
        }
        setStatus(value === "true" ? "guest" : "onboarding");
      })
      .catch(() => {
        if (mounted) {
          setStatus("onboarding");
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const value: AuthContextValue = {
    status,
    enterAsGuest: async () => {
      await storage.setItem(guestKey, "true");
      setStatus("guest");
    },
    resetOnboarding: async () => {
      await storage.removeItem(guestKey);
      setStatus("onboarding");
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
