import { createContext, useContext, useEffect, useState } from "react";
import { bootSession, type PlatformUser } from "./api";

type AuthValue = {
  user: PlatformUser | null;
  ready: boolean;
  setUser: (user: PlatformUser | null) => void;
};

const AuthContext = createContext<AuthValue>({ user: null, ready: false, setUser: () => undefined });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PlatformUser | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    bootSession()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);
  return <AuthContext.Provider value={{ user, ready, setUser }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
