import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, Category, errText, http, openCertificate } from "../api";
import { CourseManager, QuizManager } from "./AdminContent";
import { CertificateRequests, ChallengesManager, CourseEditForm, ProjectsManager, FinalResultsTab, SettingsTab, StudentEditor, SubmissionsTab, AnnouncementsTab } from "./AdminExtra";
import { CertificateDesigner } from "./AdminDesign";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;
const TABS = ["Overview", "Students", "Final results", "Submissions", "Live Activity", "Courses", "Quizzes", "Challenges", "Project Ideas", "Certificates", "Certificate Design", "Settings", "Payments", "Announcements", "Notifications", "Analytics", "Audit Logs"] as const;
type Tab = (typeof TABS)[number];
const when = (s?: string | null) => (s ? new Date(s).toLocaleString() : "never");

function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { setErr(null); http<T>(path).then(setData).catch(e => setErr(errText(e))); }, [path]);
  useEffect(load, [load]);
  return { data, err, load };
}
const Err = ({ e }: { e: string | null }) => (e ? <p role="alert" className="err">{e}</p> : null);

function Overview({ go }: { go: (t: Tab) => void }) {
  const { data, err } = useLoad<Obj>("/admin/overview");
  const cards: [string, any][] = data ? [["Registered students", data.total_students], ["Active today", data.active_today],
    ["Online now", data.online_now], ["Published courses", data.total_courses], ["Enrollments", data.total_enrollments],
    ["Completed courses", data.completed_courses], ["Quiz attempts", data.quiz_attempts], ["Certificates issued", data.certificates_issued],
    ["Verified payments", data.payments_connected ? data.verified_payments : "Not connected"]] : [];
  return <><Err e={err} />{data && data.unread_notifications > 0 && <p className="notice" role="status">🔔 {data.unread_notifications} new notification(s) (for example certificate payments). <button className="ghost" onClick={() => go("Notifications")}>Open notifications</button></p>}<div className="grid">{cards.map(([k, v]) => <div key={k} className="card"><h3>{String(v)}</h3><p className="muted">{k}</p></div>)}</div>
    <p className="muted">All numbers are counted from the database. &quot;Online&quot; uses a heartbeat with a configurable timeout.</p></>;
}

function Students() {
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [sort, setSort] = useState("registered"); const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: "10", sort });
  if (q.trim()) qs.set("q", q.trim());
  if (status) qs.set("status", status);
  const { data, err, load } = useLoad<Obj>(`/admin/students?${qs}`);
  const [detail, setDetail] = useState<Obj | null>(null);
  async function toggle(s: Obj) {
    const next = s.status === "active" ? "disabled" : "active";
    if (!window.confirm(`${next === "disabled" ? "Disable" : "Re-enable"} ${s.display_name}?`)) return;
    await http(`/admin/students/${s.id}/status`, { method: "PATCH", body: { status: next } }).catch(() => undefined);
    load();
  }
  const pages = data ? Math.max(1, Math.ceil(data.total / 10)) : 1;
  return (
    <>
      <div className="filters">
        <label>Search<input value={q} placeholder="Name, email or ID" onChange={e => { setQ(e.target.value); setPage(1); }} /></label>
        <label>Status<select value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}><option value="">All</option><option value="active">Active</option><option value="disabled">Disabled</option></select></label>
        <label>Sort by<select value={sort} onChange={e => setSort(e.target.value)}><option value="registered">Registration date</option><option value="activity">Last activity</option></select></label>
        <a className="ghost" href="/api/admin/students/export.csv">Export CSV</a>
      </div>
      <Err e={err} />
      {data && data.items.length === 0 && <p>No students match. Students appear here after they register.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table>
          <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>College</th><th>Status</th><th>Online</th><th>Last activity</th><th>Courses</th><th>Best quiz</th><th></th></tr></thead>
          <tbody>{data.items.map((s: Obj) => (
            <tr key={s.id}><td>{s.display_name}</td><td>{s.email}</td><td>{s.phone || "-"}</td><td>{s.college_name || "-"}</td><td>{s.status}</td><td>{s.online ? "Online" : `Last seen ${when(s.last_seen_at)}`}</td>
              <td>{when(s.last_activity_at)}</td><td>{s.enrollments.map((e: Obj) => `${e.course} ${e.percent}%`).join(", ") || "none"}</td>
              <td>{s.best_quiz_score ?? "-"}</td>
              <td><button className="ghost" onClick={() => http<Obj>(`/admin/students/${s.id}`).then(setDetail)}>Details</button> <button className="ghost" onClick={() => toggle(s)}>{s.status === "active" ? "Disable" : "Enable"}</button></td></tr>))}</tbody>
        </table></div>
      )}
      <div className="row pager"><button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page} of {pages}</span><button className="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button></div>
      {detail && (<>
        <StudentEditor student={detail} onSaved={() => { load(); http<Obj>(`/admin/students/${detail.id}`).then(setDetail).catch(() => undefined); }} />
        <div className="card"><h3>{detail.display_name}</h3>
          <p className="muted">Registered {when(detail.registered_at)} · last login {when(detail.last_login_at)} · last logout {when(detail.last_logout_at)} · {detail.code_submissions} code submissions</p>
          <h4>Course history</h4>{detail.course_history.length === 0 ? <p>None.</p> : <ul className="plain">{detail.course_history.map((c: Obj, i: number) => <li key={i}>{c.course}: {c.lessons_done}/{c.lessons_total} lessons ({c.percent}%){c.completed ? ", completed" : ""}, enrolled {when(c.enrolled_at)}</li>)}</ul>}
          <h4>Assessment history</h4>{detail.assessment_history.length === 0 ? <p>None.</p> : <ul className="plain">{detail.assessment_history.map((a: Obj, i: number) => <li key={i}>{a.quiz}: {a.score_pct}% ({a.passed ? "passed" : "not passed"}), {when(a.submitted_at)}</li>)}</ul>}
          <button className="ghost" onClick={() => setDetail(null)}>Close</button></div>
      </>)}
    </>
  );
}

function Live() {
  const { data, err, load } = useLoad<Obj>("/admin/live");
  useEffect(() => { const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);
  return <><Err e={err} />{data && (<>
    <h3>Online now ({data.online.length})</h3>
    <p className="muted">A student counts as online if the browser sent a heartbeat in the last {data.online_timeout_seconds} seconds.</p>
    {data.online.length === 0 ? <p>Nobody is online.</p> : <ul className="plain">{data.online.map((o: Obj) => <li key={o.id}>{o.display_name} (seen {when(o.last_seen_at)})</li>)}</ul>}
    <h3>Recent activity</h3>
    {data.recent_activity.length === 0 ? <p>No activity recorded yet.</p> : <ul className="plain">{data.recent_activity.map((a: Obj, i: number) => <li key={i}>{a.student}: {a.kind.replace("_", " ")}{a.ref ? ` (${a.ref})` : ""} · {when(a.at)}</li>)}</ul>}
    <button className="ghost" onClick={load}>Refresh</button></>)}</>;
}

function Courses() {
  const { data, err, load } = useLoad<Obj>("/admin/courses");
  const [cats, setCats] = useState<Category[]>([]);
  const [f, setF] = useState({ slug: "", title: "", category_id: "", level: "beginner", summary: "", is_paid: true, price_inr: "", project_title: "", project_description: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [managing, setManaging] = useState<number | null>(null);
  const [editing, setEditing] = useState<Obj | null>(null);
  useEffect(() => { api.categories().then(r => { setCats(r.items); setF(x => ({ ...x, category_id: r.items[0]?.id ?? "" })); }).catch(() => undefined); }, []);
  async function toggle(c: Obj) {
    if (!window.confirm(`${c.published ? "Unpublish" : "Publish"} "${c.title}"? Student progress is kept either way.`)) return;
    await http(`/admin/courses/${c.id}`, { method: "PATCH", body: { published: !c.published } }).catch(e => setMsg(errText(e)));
    load();
  }
  async function togglePaid(c: Obj) {
    const to = c.is_paid ? "FREE (no payment before the certificate)" : `PAID (Rs ${c.effective_price_inr})`;
    if (!window.confirm(`Make "${c.title}" ${to}?`)) return;
    await http(`/admin/courses/${c.id}`, { method: "PATCH", body: { is_paid: !c.is_paid } }).catch(e => setMsg(errText(e)));
    load();
  }
  async function remove(c: Obj) {
    if (!window.confirm(`Delete "${c.title}" for good? Its lessons, tests and every student's progress in it are removed. Use Unpublish if you only want to hide it.`)) return;
    setMsg(null);
    try { await http(`/admin/courses/${c.id}`, { method: "DELETE" }); setMsg("Course deleted."); load(); } catch (er) { setMsg(errText(er)); }
  }
  async function create(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await http("/admin/courses", { method: "POST", body: { ...f, price_inr: f.is_paid && f.price_inr ? Number(f.price_inr) : null } }); setMsg("Course created as a draft. Click Manage lessons to add modules and lessons, then Publish."); setF({ ...f, slug: "", title: "", summary: "", price_inr: "", project_title: "", project_description: "" }); load(); }
    catch (er) { setMsg(errText(er)); }
  }
  if (editing) return <CourseEditForm course={editing} cats={cats} onCancel={() => setEditing(null)} onDone={() => { setEditing(null); setMsg("Course saved."); load(); }} />;
  if (managing) return <CourseManager courseId={managing} onBack={() => { setManaging(null); load(); }} />;
  return (
    <>
      <Err e={err} />
      <div className="scroll"><table><thead><tr><th>Course</th><th>Published</th><th>Price</th><th>Project</th><th>Lessons</th><th>Enrollments</th><th>Completion</th><th></th></tr></thead>
        <tbody>{data?.items.map((c: Obj) => <tr key={c.id}><td>{c.title}</td><td>{c.published ? "Yes" : "No"}</td><td>{c.is_paid ? `Rs ${c.effective_price_inr}` : "Free"} <button className="ghost" onClick={() => togglePaid(c)}>{c.is_paid ? "Make free" : "Make paid"}</button></td><td>{c.project_title || "-"}</td><td>{c.lessons}</td><td>{c.enrollments}</td>
          <td>{c.completion_rate_pct === null ? "-" : `${c.completion_rate_pct}%`}</td><td><button className="ghost" onClick={() => setManaging(c.id)}>Manage lessons</button> <button className="ghost" onClick={() => setEditing(c)}>Edit</button> <button className="ghost" onClick={() => toggle(c)}>{c.published ? "Unpublish" : "Publish"}</button> <button className="ghost" onClick={() => remove(c)}>Delete</button></td></tr>)}</tbody></table></div>
      <h3>Create a course</h3>
      <form className="form" onSubmit={create}>
        <label>Slug (lowercase, dashes)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" minLength={2} value={f.slug} onChange={e => setF({ ...f, slug: e.target.value })} /></label>
        <label>Title<input required minLength={2} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} /></label>
        <label>Category<select value={f.category_id} onChange={e => setF({ ...f, category_id: e.target.value })}>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>Level<select value={f.level} onChange={e => setF({ ...f, level: e.target.value })}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
        <label>Summary<input value={f.summary} onChange={e => setF({ ...f, summary: e.target.value })} /></label>
        <label>Certificate<select value={f.is_paid ? "paid" : "free"} onChange={e => setF({ ...f, is_paid: e.target.value === "paid" })}><option value="paid">Paid</option><option value="free">Free</option></select></label>
        {f.is_paid && <label>Price in rupees (empty = default price from Settings)<input type="number" min={1} max={100000} value={f.price_inr} onChange={e => setF({ ...f, price_inr: e.target.value })} /></label>}
        <label>Project name for this course (optional)<input maxLength={160} value={f.project_title} onChange={e => setF({ ...f, project_title: e.target.value })} /></label>
        <label>Project description<textarea className="editor" rows={3} maxLength={3000} value={f.project_description} onChange={e => setF({ ...f, project_description: e.target.value })} /></label>
        <button className="solid">Create draft</button>
      </form>
      {msg && <p role="status">{msg}</p>}
      <p className="muted">Quizzes, practice sets and final exams are in the Quizzes tab, coding challenges in the Challenges tab, guided projects in the Projects tab. Each course can be Free or Paid with its own price (the default price and the payment methods are in Settings). Publishing a course that has lessons, or a challenge, notifies every student.</p>
    </>
  );
}

function Analytics() {
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const qs = new URLSearchParams(); if (from) qs.set("from", from); if (to) qs.set("to", to);
  const { data, err } = useLoad<Obj>(`/admin/analytics?${qs}`);
  const total = (s: Obj[]) => s.reduce((n, x) => n + x.count, 0);
  return (
    <>
      <div className="filters"><label>From<input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label><label>To<input type="date" value={to} onChange={e => setTo(e.target.value)} /></label></div>
      <Err e={err} />
      {data && (<>
        <p className="muted">Range {data.range.from} to {data.range.to} (UTC)</p>
        <div className="grid">
          <div className="card"><h3>{total(data.registrations)}</h3><p className="muted">New registrations</p></div>
          <div className="card"><h3>{total(data.enrollments)}</h3><p className="muted">Enrollments</p></div>
          <div className="card"><h3>{data.monthly_active}</h3><p className="muted">Monthly active students</p></div>
          <div className="card"><h3>{data.retention_7d.rate_pct === null ? "n/a" : `${data.retention_7d.rate_pct}%`}</h3><p className="muted">7-day retention ({data.retention_7d.eligible} eligible)</p></div>
          <div className="card"><h3>{data.challenges.submissions}</h3><p className="muted">Challenge submissions ({data.challenges.students} students)</p></div>
        </div>
        <h3>Daily active students</h3>
        <div className="scroll"><table><thead><tr><th>Date</th><th>Active</th><th>Registrations</th><th>Enrollments</th></tr></thead>
          <tbody>{data.daily_active.map((d: Obj, i: number) => <tr key={d.date}><td>{d.date}</td><td>{d.count}</td><td>{data.registrations[i].count}</td><td>{data.enrollments[i].count}</td></tr>)}</tbody></table></div>
        <h3>Course completion</h3>
        <ul className="plain">{data.completion.map((c: Obj) => <li key={c.course}>{c.course}: {c.completed}/{c.enrolled} completed{c.completion_rate_pct === null ? "" : ` (${c.completion_rate_pct}%)`}</li>)}</ul>
        <h3>Quiz performance</h3>
        <ul className="plain">{data.quiz_performance.map((c: Obj) => <li key={c.quiz}>{c.quiz}: {c.attempts} attempts{c.attempts ? `, average ${c.average_score_pct}%, pass rate ${c.pass_rate_pct}%` : ""}</li>)}</ul>
        <p>Revenue: {data.revenue.connected ? `Rs ${data.revenue.verified_revenue_inr} from ${data.revenue.verified_payments} verified payment(s) in this range.` : data.revenue.message} Certificates issued: {data.certificates_issued}.</p>
        <h3>How each metric is calculated</h3>
        <ul className="plain">{Object.entries(data.definitions).map(([k, v]) => <li key={k}><strong>{k.replace(/_/g, " ")}:</strong> {String(v)}</li>)}</ul>
      </>)}
    </>
  );
}

function Audit() {
  const { data, err } = useLoad<Obj>("/admin/audit-logs");
  return <><Err e={err} />{data && (data.items.length === 0 ? <p>No admin actions recorded yet.</p> :
    <div className="scroll"><table><thead><tr><th>When</th><th>Admin</th><th>Action</th><th>Target</th><th>Detail</th></tr></thead>
      <tbody>{data.items.map((a: Obj, i: number) => <tr key={i}><td>{when(a.at)}</td><td>{a.admin}</td><td>{a.action}</td><td>{a.target}</td><td>{a.detail}</td></tr>)}</tbody></table></div>)}</>;
}

function Certificates() {
  const { data, err, load } = useLoad<Obj>("/admin/certificates");
  const [msg, setMsg] = useState<string | null>(null);
  async function send(c: Obj) {
    setMsg(null);
    try { await http(`/admin/certificates/${c.id}/send-email`, { method: "POST" }); setMsg(`Certificate emailed to ${c.email}.`); load(); }
    catch (e) { setMsg(errText(e)); }
  }
  async function mark(c: Obj) {
    if (!window.confirm(`Mark the certificate for ${c.student} as sent? Do this after you emailed it yourself.`)) return;
    await http(`/admin/certificates/${c.id}/mark-sent`, { method: "POST" }).catch(e => setMsg(errText(e)));
    load();
  }
  return (
    <>
      <CertificateRequests onChange={load} />
      <h3>Issued certificates</h3>
      <Err e={err} />
      <p className="muted">A certificate appears here only after the student finished the course and the payment was verified. {data && !data.email_configured && "Email sending is not configured, so download the PDF, email it yourself, then click Mark as sent."}</p>
      {msg && <p role="status">{msg}</p>}
      {data && data.items.length === 0 && <p>No certificates yet.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table><thead><tr><th>Student</th><th>Email</th><th>Course</th><th>Issued</th><th>Delivery</th><th></th></tr></thead>
          <tbody>{data.items.map((c: Obj) => (
            <tr key={c.id}><td>{c.student}</td><td>{c.email}</td><td>{c.course}</td><td>{when(c.issued_at)}</td>
              <td>{c.delivered ? `${c.delivered.method === "email" ? "Emailed" : "Marked as sent"} ${when(c.delivered.sent_at)}` : "Not sent"}</td>
              <td><button className="ghost" onClick={() => openCertificate(c.id, "pdf").catch(e => setMsg(errText(e)))}>PDF</button>{" "}
                <button className="ghost" onClick={() => openCertificate(c.id, "png").catch(e => setMsg(errText(e)))}>Image</button>{" "}
                {data.email_configured && <button className="ghost" onClick={() => send(c)}>Send email</button>}{" "}
                <button className="ghost" onClick={() => mark(c)}>Mark as sent</button></td></tr>))}</tbody></table></div>
      )}
    </>
  );
}

function Payments() {
  const { data, err, load } = useLoad<Obj>("/admin/payments");
  const [msg, setMsg] = useState<string | null>(null);
  async function review(p: Obj, action: "confirm" | "reject") {
    let body: Obj = {};
    if (action === "confirm" && !window.confirm(`Confirm that Rs ${p.amount_inr} from ${p.student} (${p.transaction_ref}) reached your account? This unlocks the certificate.`)) return;
    if (action === "reject") { const reason = window.prompt("Reason shown to the student (for example: payment not received)", "Payment not received"); if (reason === null) return; body = { reason }; }
    setMsg(null);
    try { await http(`/admin/payments/${p.order_id}/${action}`, { method: "POST", body }); setMsg(action === "confirm" ? "Payment confirmed. The student was notified." : "Payment rejected. The student was notified."); load(); }
    catch (e) { setMsg(errText(e)); }
  }
  const items: Obj[] = data ? [...data.items].sort((a: Obj, b: Obj) => Number(b.status === "in_review") - Number(a.status === "in_review")) : [];
  const waiting = items.filter(p => p.status === "in_review").length;
  return (
    <>
      <Err e={err} />
      {data && (<>
        {data.message && <p className="notice">{data.message}</p>}
        {waiting > 0 && <p className="notice"><strong>{waiting} UPI payment(s) waiting for your confirmation.</strong> Check your bank or UPI app first.</p>}
        <p><strong>Verified revenue: Rs {data.verified_revenue_inr}</strong> <span className="muted">(verified payments only; pending orders are never counted)</span></p>
        {data.items.length === 0 ? <p>No payments yet.</p> : (
          <div className="scroll"><table><thead><tr><th>Student</th><th>Course</th><th>Amount</th><th>Method</th><th>Status</th><th>Paid</th><th>Reference</th><th></th></tr></thead>
            <tbody>{items.map((p: Obj) => <tr key={p.order_id}><td>{p.student}<small className="block">{p.email}</small></td><td>{p.course}</td><td>Rs {p.amount_inr}</td>
              <td>{p.gateway === "upi_manual" ? "Direct UPI" : `Razorpay${p.method ? ` · ${p.method}` : ""}`}</td>
              <td>{p.status === "in_review" ? "waiting for you" : p.status}{p.failure_reason ? <small className="block">{p.failure_reason}</small> : null}</td>
              <td>{when(p.paid_at)}</td><td>{p.transaction_ref ?? "-"}</td>
              <td>{p.status === "in_review" && <><button className="solid" onClick={() => review(p, "confirm")}>Confirm</button> <button className="ghost" onClick={() => review(p, "reject")}>Reject</button></>}</td></tr>)}</tbody></table></div>)}
        {msg && <p role="status">{msg}</p>}
      </>)}
    </>
  );
}

function Notifications() {
  const { data, err, load } = useLoad<Obj>("/admin/notifications");
  async function readAll() { await http("/admin/notifications/read-all", { method: "POST" }).catch(() => undefined); load(); }
  return (
    <>
      <Err e={err} />
      {data && (<>
        <p>{data.unread} unread. <button className="ghost" onClick={readAll}>Mark all as read</button> <button className="ghost" onClick={load}>Refresh</button></p>
        {data.items.length === 0 ? <p>No notifications yet. You will see certificate payments here.</p> : (
          <ul className="plain">{data.items.map((n: Obj) => (
            <li key={n.id}>{n.read ? "" : "🔔 "}<strong>{when(n.at)}</strong>: {n.message}{n.emailed ? " (also emailed to you)" : ""}</li>))}</ul>)}
      </>)}
    </>
  );
}

export default function Admin() {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <section className="page wide admin-shell">
      <h1>Admin dashboard</h1>
      <div className="tabs" role="tablist">{TABS.map(t => <button key={t} className="ghost" aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>)}</div>
      <div className="admin-main">
      {tab === "Final results" && <FinalResultsTab />}{tab === "Submissions" && <SubmissionsTab />}
      {tab === "Overview" && <Overview go={setTab} />}{tab === "Students" && <Students />}{tab === "Live Activity" && <Live />}
      {tab === "Courses" && <Courses />}{tab === "Quizzes" && <QuizManager />}{tab === "Challenges" && <ChallengesManager />}{tab === "Project Ideas" && <ProjectsManager />}{tab === "Settings" && <SettingsTab />}{tab === "Analytics" && <Analytics />}{tab === "Audit Logs" && <Audit />}{tab === "Certificates" && <Certificates />}{tab === "Certificate Design" && <CertificateDesigner />}{tab === "Announcements" && <AnnouncementsTab />}{tab === "Payments" && <Payments />}{tab === "Notifications" && <Notifications />}
      </div>
    </section>
  );
}
