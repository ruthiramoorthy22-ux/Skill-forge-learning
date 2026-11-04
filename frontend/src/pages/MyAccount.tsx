import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, EnrollmentRow, errText, http, openCertificate } from "../api";

interface FR { state: "none" | "pending" | "released"; score_pct?: number; passed?: boolean }

/** One line per joined course: where the final exam stands. The admin releases each result. */
export function Results() {
  const [rows, setRows] = useState<EnrollmentRow[] | null>(null);
  const [fr, setFr] = useState<Record<string, FR>>({});
  useEffect(() => {
    api.myEnrollments().then(r => {
      setRows(r.items);
      r.items.forEach(e => http<FR>(`/courses/${e.course_slug}/final-result`).then(x => setFr(p => ({ ...p, [e.course_slug]: x }))).catch(() => undefined));
    }).catch(() => setRows([]));
  }, []);
  return (
    <section className="page narrow">
      <h1>My results</h1>
      {rows && rows.length === 0 && <p>You have not joined a course yet. <Link to="/courses">Browse courses</Link>.</p>}
      <div className="tiles">
        {rows?.map(r => {
          const x = fr[r.course_slug];
          const text = !x || x.state === "none" ? "Final exam not taken yet" : x.state === "pending" ? "Submitted. Waiting for the admin to release your result" : `${x.score_pct}% · ${x.passed ? "Passed" : "Not passed"}`;
          const icon = !x || x.state === "none" ? "📘" : x.state === "pending" ? "⏳" : x.passed ? "✅" : "❌";
          return (
            <Link key={r.course_slug} className="tile" to={x && x.state !== "none" ? `/courses/${r.course_slug}/result` : `/courses/${r.course_slug}`}>
              <span className="tile-ico">{icon}</span><span><strong>{r.title}</strong><small>{text}</small></span><span className="go">›</span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

export function Certificates() {
  const [certs, setCerts] = useState<{ id: string; course: string }[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { http<{ items: { id: string; course: string }[] }>("/me/certificates").then(r => setCerts(r.items)).catch(() => setCerts([])); }, []);
  return (
    <section className="page narrow">
      <h1>My certificates</h1>
      {certs && certs.length === 0 && <p>No certificate yet. Finish a course, see your result and pay to receive it.</p>}
      <div className="tiles">
        {certs?.map(c => (
          <div key={c.id} className="card"><h3>🏅 {c.course}</h3>
            <div className="row"><button className="solid" onClick={() => openCertificate(c.id, "pdf").catch(e => setMsg(errText(e)))}>PDF</button>
              <button className="ghost" onClick={() => openCertificate(c.id, "png").catch(e => setMsg(errText(e)))}>Image</button></div></div>
        ))}
      </div>
      {msg && <p role="alert" className="err">{msg}</p>}
    </section>
  );
}
