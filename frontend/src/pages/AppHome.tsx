import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, EnrollmentRow, http } from "../api";
import { useAuth } from "../auth";
import { useDrawer } from "../components/Drawer";
import Illustration from "../components/Illustration";
import { useAvatar } from "../components/Avatar";
import NotificationBell from "../components/NotificationBell";

interface Stats { xp: number; streak: number; lessons: number; courses_completed: number }
interface Rec { type: "lesson" | "course"; course_slug: string; lesson_slug?: string; title: string }

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good Morning" : h < 17 ? "Good Afternoon" : "Good Evening";
}

/** Home screen: greeting, hero card, quick actions, overall progress and the student's courses. */
export default function AppHome() {
  const { user } = useAuth();
  const drawer = useDrawer();
  const [rows, setRows] = useState<EnrollmentRow[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [recs, setRecs] = useState<Rec[]>([]);
  useEffect(() => {
    api.myEnrollments().then(r => setRows(r.items)).catch(() => setRows([]));
    http<Stats>("/me/stats").then(setStats).catch(() => undefined);
    http<{ items: Rec[] }>("/me/recommendations").then(r => setRecs(r.items)).catch(() => undefined);
  }, []);
  const pic = useAvatar();
  if (!user) return null;
  const overall = rows && rows.length ? Math.round(rows.reduce((a, r) => a + r.percent, 0) / rows.length) : 0;
  const initials = user.display_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const R = 30, C = 2 * Math.PI * R;
  const actions: [string, string, string][] = [["/courses", "📚", "Courses"], ["/challenges", "💻", "Practice"], ["/results", "📝", "Results"], ["/certificates", "🏅", "Certificates"]];
  const resume = rows?.find(r => r.percent < 100);

  return (
    <section className="home">
      <header className="home-head">
        <button className="icon-btn" onClick={drawer.open} aria-label="Open menu">☰</button>
        <div className="who"><small>{greeting()},</small><strong>{user.display_name}</strong></div>
        <NotificationBell />
        <Link to="/profile" className="avatar sm" aria-label="My profile">{pic ? <img src={pic} alt="" /> : initials}</Link>
      </header>

      <div className="hero-card">
        <div>
          <h2>{resume ? "Pick up where you left off" : "Start your learning journey"}</h2>
          <p>{stats ? `${stats.streak}-day streak · ${stats.xp} XP` : "Learn, practise and earn a certificate."}</p>
          <Link className="hero-btn" to={resume ? (resume.last_lesson ? `/courses/${resume.course_slug}/lessons/${resume.last_lesson}` : `/courses/${resume.course_slug}`) : "/courses"}>
            {resume ? "Continue" : "Browse courses"}
          </Link>
        </div>
        <Illustration variant="boy" />
      </div>

      <div className="quick">
        {actions.map(([to, icon, label]) => <Link key={to} to={to}><span className="qi" aria-hidden="true">{icon}</span><small>{label}</small></Link>)}
      </div>

      <div className="ready-card">
        <div><small>Overall progress</small><strong>{overall}%</strong><span className="muted">{rows ? `${rows.length} course${rows.length === 1 ? "" : "s"} joined` : "Loading…"}</span></div>
        <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label={`Overall progress ${overall}%`}>
          <circle cx="38" cy="38" r={R} fill="none" stroke="var(--line)" strokeWidth="7" />
          <circle cx="38" cy="38" r={R} fill="none" stroke="var(--good)" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={C} strokeDashoffset={C * (1 - overall / 100)} transform="rotate(-90 38 38)" />
          <text x="38" y="43" textAnchor="middle" fontSize="15" fontWeight="700" fill="var(--ink)">{overall}%</text>
        </svg>
      </div>

      <div className="sec-head"><h3>My courses</h3><Link to="/dashboard">See all</Link></div>
      {rows && rows.length === 0 && <p className="muted">You have not joined a course yet. <Link to="/courses">Browse the catalog</Link>.</p>}
      <div className="h-scroll">
        {rows?.map(r => (
          <Link key={r.course_slug} className="mini-course" to={r.last_lesson ? `/courses/${r.course_slug}/lessons/${r.last_lesson}` : `/courses/${r.course_slug}`}>
            <strong>{r.title}</strong><small>{r.completed} of {r.total} lessons</small>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${r.percent}%` }} /></div>
          </Link>
        ))}
        {recs.filter(r => r.type === "course").map(r => (
          <Link key={r.course_slug} className="mini-course new" to={`/courses/${r.course_slug}`}><strong>{r.title}</strong><small>New for you · tap to start</small></Link>
        ))}
      </div>
    </section>
  );
}
