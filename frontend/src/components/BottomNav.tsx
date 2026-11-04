import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

/** Four tabs only: Home, Courses, Practice, Profile. Hidden on sign-in, lessons, quizzes and the admin area. */
export default function BottomNav() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  if (pathname.startsWith("/admin") || pathname.includes("/lessons/") || pathname.startsWith("/quizzes/") || ["/signin", "/register"].includes(pathname)) return null;
  const items: [string, string, string][] = [
    [user ? "/home" : "/signin", "🏠", "Home"],
    ["/courses", "📚", "Courses"],
    ["/challenges", "💻", "Practice"],
    [user ? (user.role === "admin" ? "/admin" : "/profile") : "/signin", "👤", "Profile"],
  ];
  return (
    <nav className="bottomnav" aria-label="App">
      {items.map(([to, icon, label]) => (
        <NavLink key={label} to={to} end={to === "/home"}>
          <span aria-hidden="true" className="ico">{icon}</span><span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
