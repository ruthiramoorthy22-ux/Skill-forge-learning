import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Catalog from "./pages/Catalog";
import { About, Help, Paths, Privacy, Projects, Terms } from "./pages/Static";
import { AdminLogin, Register, SignIn } from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Profile from "./pages/Profile";
import Admin from "./pages/Admin";
import CourseDetailPage from "./pages/CourseDetail";
import LessonPage from "./pages/Lesson";
import Playground from "./pages/Playground";
import { ChallengeDetail, ChallengeList } from "./pages/Challenges";
import Quiz from "./pages/Quiz";
import AppHome from "./pages/AppHome";
import { Certificates, Results } from "./pages/MyAccount";
import { FinalResultPage, PayPage } from "./pages/ResultPay";
import { PaymentFailed, PaymentHistoryPage, PaymentSuccess } from "./pages/Payments";
import Notifications from "./pages/Notifications";
import NotificationBell from "./components/NotificationBell";
import { DrawerProvider } from "./components/Drawer";
import { RequireAuth, useAuth } from "./auth";
import { isApp } from "./api";
import BottomNav from "./components/BottomNav";
import BrandLogo from "./components/BrandLogo";

type Theme = "light" | "dark";

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try { const s = localStorage.getItem("sf-theme"); if (s === "light" || s === "dark") return s; } catch { /* ignore */ }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("sf-theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return [theme, () => setTheme(theme === "light" ? "dark" : "light")];
}

const nav = [["/courses", "Courses"], ["/challenges", "Challenges"], ["/playground", "Playground"], ["/paths", "Learning paths"], ["/projects", "Projects"], ["/about", "About"], ["/help", "Help"]];

const appNav = [["/home", "Home"], ["/courses", "Courses"], ["/challenges", "Challenges"], ["/playground", "Playground"]];

/** In the Android app the first screen is the sign-in page (or the dashboard when already signed in). */
function AppEntry() {
  const { user, loading } = useAuth();
  if (loading) return <section className="page brand-loading"><BrandLogo /><p aria-live="polite">Loading Skill Forge Learning…</p></section>;
  return <Navigate to={user ? (user.role === "admin" ? "/admin" : "/home") : "/signin"} replace />;
}

export default function App() {
  const [theme, toggle] = useTheme();
  const { user, loading, signOut } = useAuth();
  return (
    <DrawerProvider dark={theme === "dark"} toggleTheme={toggle}>
      <a className="skip" href="#main">Skip to content</a>
      <header className="bar">
        <Link to="/" className="brand" aria-label="Skill Forge Learning home">
          <BrandLogo /> Skill Forge Learning
        </Link>
        <nav aria-label="Main">
          {(isApp ? appNav : nav).map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <div className="actions">
          <button className="ghost" onClick={toggle} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}>
            {theme === "light" ? "Dark" : "Light"}
          </button>
          {!loading && user?.role === "admin" ? (
            <>
              <NotificationBell />
              <Link className="ghost who" to="/admin">{user.display_name}</Link>
              <button className="solid" onClick={signOut}>Sign out</button>
            </>
          ) : !loading && !user ? (
            <>
              <Link className="ghost" to="/signin">Sign in</Link>
              <Link className="solid" to="/register">Register</Link>
            </>
          ) : null}
        </div>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={isApp ? <AppEntry /> : <Home />} />
          <Route path="/courses" element={<Catalog />} />
          <Route path="/courses/:slug" element={<CourseDetailPage />} />
          <Route path="/courses/:slug/lessons/:lessonSlug" element={<RequireAuth><LessonPage /></RequireAuth>} />
          <Route path="/playground" element={<RequireAuth><Playground /></RequireAuth>} />
          <Route path="/challenges" element={<ChallengeList />} />
          <Route path="/challenges/:slug" element={<ChallengeDetail />} />
          <Route path="/quizzes/:id" element={<RequireAuth><Quiz /></RequireAuth>} />
          <Route path="/paths" element={<Paths />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/about" element={<About />} />
          <Route path="/help" element={<Help />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/register" element={<Register />} />
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route path="/home" element={<RequireAuth><AppHome /></RequireAuth>} />
          <Route path="/results" element={<RequireAuth><Results /></RequireAuth>} />
          <Route path="/certificates" element={<RequireAuth><Certificates /></RequireAuth>} />
          <Route path="/courses/:slug/result" element={<RequireAuth><FinalResultPage /></RequireAuth>} />
          <Route path="/courses/:slug/pay" element={<RequireAuth><PayPage /></RequireAuth>} />
          <Route path="/payments" element={<RequireAuth><PaymentHistoryPage /></RequireAuth>} />
          <Route path="/payment/success/:id" element={<RequireAuth><PaymentSuccess /></RequireAuth>} />
          <Route path="/payment/failed/:id" element={<RequireAuth><PaymentFailed /></RequireAuth>} />
          <Route path="/notifications" element={<RequireAuth><Notifications /></RequireAuth>} />
          <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
          <Route path="/admin" element={<RequireAuth admin><Admin /></RequireAuth>} />
          <Route path="*" element={<section className="page"><h1>Page not found</h1><p><Link to="/">Return to the home page</Link></p></section>} />
        </Routes>
      </main>
      <BottomNav />
      <footer className="foot">
        <span>Skill Forge Learning</span>
        <Link to="/privacy">Privacy Policy</Link>
        <Link to="/terms">Terms of Service</Link>
        <Link to="/help">Help</Link>
        <Link to="/admin/login">Admin</Link>
      </footer>
    </DrawerProvider>
  );
}
