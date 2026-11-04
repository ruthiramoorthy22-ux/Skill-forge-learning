import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import Avatar, { useAvatar } from "./Avatar";

const Ctx = createContext<{ open: () => void }>({ open: () => undefined });
export const useDrawer = () => useContext(Ctx);

/** Side menu opened from the hamburger button on the Home screen. */
export function DrawerProvider({ children, dark, toggleTheme }: { children: ReactNode; dark: boolean; toggleTheme: () => void }) {
  const [isOpen, setOpen] = useState(false);
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  const pic = useAvatar();
  const items: [string, string, string][] = user ? [
    ["/home", "🏠", "Home"], ["/profile", "👤", "My profile"], ["/courses", "📚", "Courses"], ["/results", "📝", "My results"],
    ["/certificates", "🏅", "My certificates"], ["/payments", "💳", "Payment history"], ["/notifications", "🔔", "Notifications"], ["/dashboard", "📈", "My progress"], ["/help", "❓", "Help"],
    ...(user.role === "admin" ? [["/admin", "🛠️", "Admin"] as [string, string, string]] : []),
  ] : [["/signin", "🔑", "Sign in"], ["/courses", "📚", "Courses"], ["/help", "❓", "Help"]];
  return (
    <Ctx.Provider value={{ open: () => setOpen(true) }}>
      {children}
      <div className={`drawer-scrim ${isOpen ? "show" : ""}`} onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className={`drawer ${isOpen ? "show" : ""}`} aria-label="Menu" aria-hidden={!isOpen}>
        <div className="drawer-head">
          <Avatar name={user?.display_name ?? ""} src={user?.role === "admin" ? "" : pic} />
          <div><strong>{user?.display_name ?? "Skill Learning"}</strong><small>{user?.email ?? "Welcome"}</small></div>
        </div>
        <nav>
          {items.map(([to, icon, label]) => <Link key={to} to={to} onClick={() => setOpen(false)}><span aria-hidden="true">{icon}</span>{label}</Link>)}
          <button onClick={toggleTheme}><span aria-hidden="true">{dark ? "☀️" : "🌙"}</span>{dark ? "Light mode" : "Dark mode"}</button>
          {user && <button className="danger" onClick={() => { setOpen(false); signOut(); }}><span aria-hidden="true">🚪</span>Sign out</button>}
        </nav>
        <small className="drawer-foot">Skill Learning</small>
      </aside>
    </Ctx.Provider>
  );
}
