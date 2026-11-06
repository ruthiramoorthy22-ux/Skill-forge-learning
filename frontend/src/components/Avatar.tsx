import { useEffect, useState } from "react";
import { http } from "../api";
import { useAuth } from "../auth";

let cache: string | null = null;
let cacheUser: string | null = null;
const subs = new Set<(v: string) => void>();

/** Call after the student uploads or removes the picture so every place that shows it updates. */
export function setAvatarCache(v: string) { cache = v; subs.forEach(f => f(v)); }

/** The signed-in student's profile picture (a data URL) or "" when there is none. */
export function useAvatar(): string {
  const { user } = useAuth();
  const [v, setV] = useState(cache ?? "");
  useEffect(() => { subs.add(setV); return () => { subs.delete(setV); }; }, []);
  useEffect(() => {
    if (!user || user.role === "admin") return;
    if (cacheUser !== user.id) { cache = null; cacheUser = user.id; setV(""); }
    if (cache === null) http<{ avatar: string }>("/me/avatar").then(r => setAvatarCache(r.avatar)).catch(() => undefined);
    else setV(cache);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return v;
}

/** Round picture, or the initials when the student has not added one. */
export default function Avatar({ name, src, className = "" }: { name: string; src?: string; className?: string }) {
  const initials = name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase() || "SF";
  return <span className={`avatar ${className}`} aria-hidden="true">{src ? <img src={src} alt="" /> : initials}</span>;
}
