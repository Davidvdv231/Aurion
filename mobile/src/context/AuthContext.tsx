import React, { createContext, useContext, useEffect, useState } from "react";

import { createAsyncStorageAdapter } from "@/storage/storage";

type AuthStatus = "loading" | "signedOut" | "signedIn";

interface AuthContextValue {
  status: AuthStatus;
  email: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const authKey = "demo-auth-v1";
const storage = createAsyncStorageAdapter();
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    storage
      .getItem(authKey)
      .then((value) => {
        if (!mounted) {
          return;
        }
        if (value) {
          setEmail(value);
          setStatus("signedIn");
        } else {
          setStatus("signedOut");
        }
      })
      .catch(() => {
        if (mounted) {
          setStatus("signedOut");
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const value: AuthContextValue = {
    status,
    email,
    signIn: async (nextEmail: string) => {
      await storage.setItem(authKey, nextEmail);
      setEmail(nextEmail);
      setStatus("signedIn");
    },
    signOut: async () => {
      await storage.removeItem(authKey);
      setEmail(null);
      setStatus("signedOut");
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
