import { FormEvent, useEffect, useState } from "react";
import { errText, http } from "../api";

interface Sub { title: string; description: string; repo_url: string; demo_url: string; status: "submitted" | "approved" | "changes_requested"; admin_feedback: string; submitted_at: string }
interface Info { can_submit: boolean; submission: Sub | null; assigned: { title: string; description: string } | null }

const LABEL = { submitted: "Waiting for admin review", approved: "Approved", changes_requested: "Changes requested" } as const;

/** Optional student project submission for practice and feedback from the admin. */
export default function ProjectSubmit({ slug, onChange }: { slug: string; onChange: () => void }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [f, setF] = useState({ title: "", description: "", repo_url: "", demo_url: "" });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => http<Info>(`/courses/${slug}/project`).then(i => {
    setInfo(i);
    if (i.submission) setF({ title: i.submission.title, description: i.submission.description, repo_url: i.submission.repo_url, demo_url: i.submission.demo_url });
    else if (i.assigned) setF(x => ({ ...x, title: i.assigned!.title }));
  }).catch(e => setMsg(errText(e)));
  useEffect(() => { load(); }, [slug]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try { await http(`/courses/${slug}/project`, { method: "PUT", body: f }); setEditing(false); await load(); onChange(); }
    catch (er) { setMsg(errText(er)); } finally { setBusy(false); }
  }
  if (!info) return msg ? <p role="alert" className="err">{msg}</p> : null;
  const s = info.submission;
  const showForm = info.can_submit && (!s || s.status === "changes_requested" || editing);

  return (
    <div className="card project-card">
      {info.assigned && (
        <div className="assigned">
          <p className="muted">Your project for this course</p>
          <h3>📌 {info.assigned.title}</h3>
          {info.assigned.description && <p style={{ whiteSpace: "pre-wrap" }}>{info.assigned.description}</p>}
        </div>
      )}
      {!info.can_submit && !s && <p className="muted">🔒 Finish every lesson, the lesson tests and the final exam to unlock project submission.</p>}
      {s && (
        <>
          <p><span className={`status ${s.status}`}>{LABEL[s.status]}</span></p>
          <h3>{s.title}</h3>
          <p>{s.description}</p>
          <p className="links">
            {s.repo_url && <a href={s.repo_url} target="_blank" rel="noopener noreferrer">Source code</a>}
            {s.demo_url && <a href={s.demo_url} target="_blank" rel="noopener noreferrer">Live demo</a>}
          </p>
          {s.status === "changes_requested" && <div className="notice"><strong>Admin feedback:</strong> {s.admin_feedback}</div>}
          {s.status === "approved" && <p className="ok">✓ Your project was approved.</p>}
          {s.status === "submitted" && !editing && info.can_submit && <button className="ghost" onClick={() => setEditing(true)}>Edit my submission</button>}
        </>
      )}
      {showForm && (
        <form className="form-grid" onSubmit={submit}>
          <h3>{s ? "Update and submit again" : "Submit your project"}</h3>
          <label>Project name<input required minLength={3} maxLength={120} value={f.title} readOnly={!!info.assigned} onChange={e => setF({ ...f, title: e.target.value })} /></label>
          <label>What did you build? (at least 20 characters)<textarea className="editor" required minLength={20} maxLength={3000} rows={5} value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></label>
          <label>Source code link (GitHub, optional)<input type="url" maxLength={300} placeholder="https://github.com/you/project" value={f.repo_url} onChange={e => setF({ ...f, repo_url: e.target.value })} /></label>
          <label>Live demo link (optional)<input type="url" maxLength={300} placeholder="https://" value={f.demo_url} onChange={e => setF({ ...f, demo_url: e.target.value })} /></label>
          <div className="row"><button className="solid" disabled={busy}>{busy ? "Submitting…" : "Submit to admin"}</button>{editing && <button type="button" className="ghost" onClick={() => setEditing(false)}>Cancel</button>}</div>
        </form>
      )}
      {msg && <p role="alert" className="err">{msg}</p>}
    </div>
  );
}
