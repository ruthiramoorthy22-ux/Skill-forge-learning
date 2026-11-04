import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import Illustration from "../components/Illustration";

type Mode = "signin" | "register" | "admin";
const TITLES: Record<Mode, string> = { signin: "Sign In", register: "Create account", admin: "Administrator sign in" };

function AuthForm({ mode }: { mode: Mode }) {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const user = mode === "register" ? await api.register({ email, display_name: name, password })
        : mode === "admin" ? await api.adminLogin({ email, password })
        : await api.login({ email, password });
      setUser(user);
      nav(mode === "admin" || user.role === "admin" ? "/admin" : "/home", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally { setBusy(false); }
  }

  return (
    <div className="auth-screen">
      <div className="auth-top">
        <span className="auth-logo" aria-hidden="true">SL</span>
        <div className="auth-copy">
          {mode === "register" ? (<><p>Hello!</p><h1>Create your account and start learning</h1></>)
            : mode === "admin" ? (<><p>Admin</p><h1>Manage Skill Learning</h1></>)
            : (<><p>Welcome Back!</p><h1>Let&apos;s continue your learning journey</h1></>)}
        </div>
        <Illustration variant="girl" />
      </div>
      <form className="auth-sheet" onSubmit={submit}>
        {mode === "register" && (
          <label className="field-label">Full name
            <span className="field"><span aria-hidden="true">👤</span><input required maxLength={80} value={name} onChange={e => setName(e.target.value)} autoComplete="name" placeholder="Your name (shown on the certificate)" /></span>
          </label>
        )}
        <label className="field-label">Email
          <span className="field"><span aria-hidden="true">✉️</span><input required type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com" /></span>
        </label>
        <label className="field-label">Password
          <span className="field"><span aria-hidden="true">🔒</span>
            <input required type={show ? "text" : "password"} minLength={mode === "register" ? 10 : 1} value={password} onChange={e => setPassword(e.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"} placeholder={mode === "register" ? "At least 10 characters" : "Your password"} />
            <button type="button" className="eye" onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}>{show ? "🙈" : "👁️"}</button>
          </span>
        </label>
        {error && <p role="alert" className="err">{error}</p>}
        <button className="auth-btn" disabled={busy}>{busy ? "Please wait…" : <>{TITLES[mode]} <span aria-hidden="true">→</span></>}</button>
        {mode === "signin" && <p className="auth-alt">New here? <Link to="/register">Create an account</Link></p>}
        {mode === "register" && <p className="auth-alt">Already registered? <Link to="/signin">Sign in</Link></p>}
        {mode === "admin" && <p className="muted">Administrator accounts are provisioned by the site owner.</p>}
      </form>
    </div>
  );
}

export const SignIn = () => <AuthForm mode="signin" />;
export const Register = () => <AuthForm mode="register" />;
export const AdminLogin = () => <AuthForm mode="admin" />;
