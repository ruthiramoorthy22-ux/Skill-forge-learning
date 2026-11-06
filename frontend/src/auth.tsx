import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, http, User } from "./api";
import BrandLogo from "./components/BrandLogo";

function Loading() {
  return <section className="page brand-loading"><BrandLogo /><p aria-live="polite">Loading Skill Forge Learning…</p></section>;
}

interface AuthValue {
  user: User | null;
  loading: boolean;
  setUser: (u: User | null) => void;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthValue>({ user: null, loading: true, setUser: () => undefined, signOut: async () => undefined });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!user) return;
    const beat = () => { http("/activity/heartbeat", { method: "POST" }).catch(() => undefined); };
    beat();
    const t = setInterval(beat, 60000);
    return () => clearInterval(t);
  }, [user?.id]);
  const signOut = async () => { try { await api.logout(); } finally { setUser(null); } };
  return <Ctx.Provider value={{ user, loading, setUser, signOut }}>{children}</Ctx.Provider>;
}

/** UI convenience only. The server enforces access on every API call. */
export function RequireAuth({ admin, children }: { admin?: boolean; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={admin ? "/admin/login" : "/signin"} replace />;
  if (admin && user.role !== "admin") {
    return <section className="page"><h1>Not authorized</h1><p>This account does not have administrator access.</p></section>;
  }
  return <>{children}</>;
}
