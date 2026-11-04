import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, EnrollmentRow, errText, http, openCertificate } from "../api";
import { useAuth } from "../auth";
import { PaymentHistory } from "./Payments";

interface Stats {
  xp: number; streak: number; lessons: number; today_lessons: number; daily_goal: number; quizzes_passed: number;
  challenges_solved: number; courses_completed: number; show_on_leaderboard: boolean;
  achievements: { code: string; title: string; description: string; earned: boolean }[];
  recent_activity: { kind: string; ref: string | null; at: string }[];
}
interface Rec { type: "lesson" | "course"; course_slug: string; lesson_slug?: string; title: string }

export default function Dashboard() {
  const { user } = useAuth();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [rows, setRows] = useState<EnrollmentRow[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [recs, setRecs] = useState<Rec[]>([]);
  const [board, setBoard] = useState<{ display_name: string; xp: number }[]>([]);
  const [loadErr, setLoadErr] = useState(false);
  const [certs, setCerts] = useState<{ id: string; course: string }[]>([]);

  const loadStats = () => http<Stats>("/me/stats").then(setStats).catch(() => setLoadErr(true));
  useEffect(() => {
    api.myEnrollments().then(r => setRows(r.items)).catch(() => setLoadErr(true));
    loadStats();
    http<{ items: typeof certs }>("/me/certificates").then(r => setCerts(r.items)).catch(() => undefined);
    http<{ items: Rec[] }>("/me/recommendations").then(r => setRecs(r.items)).catch(() => undefined);
    http<{ items: typeof board }>("/leaderboard").then(r => setBoard(r.items)).catch(() => undefined);
  }, []);
  if (!user) return null;

  async function togglePrivacy(v: boolean) {
    await http("/me/privacy", { method: "PATCH", body: { show_on_leaderboard: v } }).catch(() => undefined);
    loadStats();
    http<{ items: typeof board }>("/leaderboard").then(r => setBoard(r.items)).catch(() => undefined);
  }

  return (
    <section className="page">
      <h1>Welcome, {user.display_name}</h1>
      {loadErr && <p role="alert" className="err">Some dashboard data could not be loaded.</p>}
      {stats && (
        <div className="grid">
          <div className="card"><h3>{stats.xp} XP</h3><p className="muted">Earned once per lesson, quiz pass, solved challenge and course.</p></div>
          <div className="card"><h3>{stats.streak}-day streak</h3><p className="muted">Days in a row with a lesson, quiz or challenge.</p></div>
          <div className="card"><h3>Daily goal</h3><p>{Math.min(stats.today_lessons, stats.daily_goal)} of {stats.daily_goal} lesson today</p>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, 100 * stats.today_lessons / stats.daily_goal)}%` }} /></div></div>
          <div className="card"><h3>Totals</h3><p className="muted">{stats.lessons} lessons · {stats.quizzes_passed} quizzes passed · {stats.challenges_solved} challenges · {stats.courses_completed} courses completed</p></div>
        </div>
      )}
      <h2>Your courses</h2>
      {!rows && !loadErr && <p aria-live="polite">Loading…</p>}
      {rows && rows.length === 0 && <p>You have not enrolled in any course yet. <Link to="/courses">Browse the catalog</Link> and pick one marked Available.</p>}
      <ul className="grid">
        {rows?.map(r => (
          <li key={r.course_slug} className="card">
            <h3>{r.title}</h3>
            <p className="muted">{r.completed} of {r.total} lessons · {r.percent}%</p>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${r.percent}%` }} /></div>
            <p><Link to={r.last_lesson ? `/courses/${r.course_slug}/lessons/${r.last_lesson}` : `/courses/${r.course_slug}`}>{r.completed ? "Continue learning" : "Start learning"}</Link></p>
          </li>
        ))}
      </ul>
      {certs.length > 0 && (<><h2>My certificates</h2><ul className="grid">{certs.map(c => (
        <li key={c.id} className="card"><h3>🏅 {c.course}</h3>
          <div className="row"><button className="solid" onClick={() => openCertificate(c.id, "pdf").catch(e => setMsg({ ok: false, text: errText(e) }))}>PDF</button>
            <button className="ghost" onClick={() => openCertificate(c.id, "png").catch(e => setMsg({ ok: false, text: errText(e) }))}>Image</button></div></li>))}</ul></>)}
      <h2>Payment history</h2>
      <PaymentHistory compact />
      {recs.length > 0 && (<><h2>Recommended next</h2><ul className="plain">{recs.map((r, i) => (
        <li key={i}>{r.type === "lesson" ? <Link to={`/courses/${r.course_slug}/lessons/${r.lesson_slug}`}>Next lesson: {r.title}</Link> : <Link to={`/courses/${r.course_slug}`}>Try the {r.title} course</Link>}</li>))}</ul></>)}
      {stats && (<>
        <h2>Achievements</h2>
        <ul className="grid">{stats.achievements.map(a => (
          <li key={a.code} className="card"><h3>{a.earned ? "✓ " : ""}{a.title}</h3><p className="muted">{a.description}</p><p>{a.earned ? "Earned" : "Not yet"}</p></li>))}</ul>
        <h2>Recent activity</h2>
        {stats.recent_activity.length === 0 ? <p>No activity yet.</p> : <ul className="plain">{stats.recent_activity.map((e, i) => <li key={i}>{e.kind.replace("_", " ")}{e.ref ? ` (${e.ref})` : ""} · {new Date(e.at).toLocaleString()}</li>)}</ul>}
        <h2>Leaderboard</h2>
        <label className="opt"><input type="checkbox" checked={stats.show_on_leaderboard} onChange={e => togglePrivacy(e.target.checked)} /> Show my display name and XP on the leaderboard (off by default)</label>
        {board.length === 0 ? <p className="muted">Nobody has opted in yet.</p> : <ol>{board.map((b, i) => <li key={i}>{b.display_name}: {b.xp} XP</li>)}</ol>}
      </>)}
      <h2>Profile</h2>
      <div className="card" style={{ maxWidth: 480 }}>
        <p className="muted">{user.email} · joined {new Date(user.created_at).toLocaleDateString()}</p>
        <p>Add your phone number, college and school details.</p>
        <Link className="solid" to="/profile">Open my profile</Link>
      </div>
    </section>
  );
}
