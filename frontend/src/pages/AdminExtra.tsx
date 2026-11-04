import { FormEvent, useCallback, useEffect, useState } from "react";
import { Category, errText, http } from "../api";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;

function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { if (!path) return; setErr(null); http<T>(path).then(setData).catch(e => setErr(errText(e))); }, [path]);
  useEffect(load, [load]);
  return { data, err, load };
}
const Err = ({ e }: { e: string | null }) => (e ? <p role="alert" className="err">{e}</p> : null);

/** One price for every course, and who releases the certificate after payment. */
export function SettingsTab() {
  const { data, err, load } = useLoad<Obj>("/admin/settings");
  const [price, setPrice] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (data) setPrice(String(data.certificate_price_inr)); }, [data]);
  async function save(body: Obj, done: string) {
    setMsg(null);
    try { await http("/admin/settings", { method: "PATCH", body }); setMsg(done); load(); } catch (e) { setMsg(errText(e)); }
  }
  return (
    <>
      <Err e={err} />
      <div className="card" style={{ maxWidth: 520 }}>
        <h3>Certificate price (all courses)</h3>
        <p className="muted">One price applies to every course. Changing it affects the next payment; earlier payments are not changed.</p>
        <form className="form" onSubmit={(e: FormEvent) => { e.preventDefault(); save({ certificate_price_inr: Number(price) }, `Price saved: Rs ${price} for every course.`); }}>
          <label>Price in rupees<input type="number" min={1} max={100000} step={1} required value={price} onChange={e => setPrice(e.target.value)} /></label>
          <button className="solid">Save price</button>
        </form>
      </div>
      <div className="card" style={{ maxWidth: 520, marginTop: 16 }}>
        <h3>After a student pays</h3>
        <label className="opt"><input type="radio" name="rel" checked={data?.certificate_release === "auto"} onChange={() => save({ certificate_release: "auto" }, "Certificates are issued automatically after payment.")} /> Issue the certificate automatically</label>
        <label className="opt"><input type="radio" name="rel" checked={data?.certificate_release === "admin"} onChange={() => save({ certificate_release: "admin" }, "Certificates now wait for you to unlock them (Certificates tab).")} /> Keep it locked until I unlock it</label>
        <p className="muted">You always get a notification when a student pays. In both modes you can unlock a certificate yourself and email it.</p>
      </div>
      <div className="card" style={{ maxWidth: 520, marginTop: 16 }}>
        <h3>Project before certificate</h3>
        <label className="opt"><input type="checkbox" checked={data?.project_required !== false} onChange={e => save({ project_required: e.target.checked }, e.target.checked ? "Students must submit a project and you must approve it." : "The project is no longer required for a certificate.")} /> Students must submit a project and get it approved</label>
        <p className="muted">When on, a student pays only after you approve the project, and the project name is printed on the certificate.</p>
      </div>
      <PaymentMethodsCard />
      {msg && <p role="status">{msg}</p>}
    </>
  );
}

/** The admin chooses how students can pay: Razorpay (UPI, GPay, PhonePe, cards, net banking), direct UPI, or both. */
function PaymentMethodsCard() {
  const { data, err, load } = useLoad<Obj>("/admin/payment-settings");
  const [upiId, setUpiId] = useState("");
  const [payee, setPayee] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (data) { setUpiId(data.upi_id); setPayee(data.upi_payee_name); } }, [data]);
  async function save(body: Obj, done: string) {
    setMsg(null);
    try { await http("/admin/payment-settings", { method: "PATCH", body }); setMsg(done); load(); } catch (e) { setMsg(errText(e)); }
  }
  const ALL: [string, string][] = [["upi", "UPI (Google Pay, PhonePe, Paytm)"], ["card", "Cards"], ["netbanking", "Net banking"], ["wallet", "Wallets"]];
  const toggleMethod = (m: string, on: boolean) => {
    const next = on ? [...data!.razorpay_methods, m] : data!.razorpay_methods.filter((x: string) => x !== m);
    save({ razorpay_methods: next }, "Razorpay methods saved.");
  };
  return (
    <div className="card" style={{ maxWidth: 520, marginTop: 16 }}>
      <h3>Payment methods</h3>
      <Err e={err} />
      {data && (<>
        <p className="muted">Choose how students can pay. Keep at least one on. Students see only what is on here.</p>
        <label className="opt"><input type="checkbox" checked={data.razorpay_enabled} onChange={e => save({ razorpay_enabled: e.target.checked }, e.target.checked ? "Razorpay is on." : "Razorpay is off.")} /> <strong>Razorpay</strong> (automatic confirmation)</label>
        <p className="muted">Keys: {data.razorpay_configured ? `set (${data.razorpay_mode.toUpperCase()} mode)` : "NOT set. Add them to backend/.env"} · Webhook secret: {data.webhook_configured ? "set" : "not set"}</p>
        {data.razorpay_enabled && ALL.map(([m, label]) => (
          <label key={m} className="opt" style={{ marginLeft: 22 }}><input type="checkbox" checked={data.razorpay_methods.includes(m)} disabled={data.razorpay_methods.length === 1 && data.razorpay_methods.includes(m)} onChange={e => toggleMethod(m, e.target.checked)} /> {label}</label>))}
        <hr />
        <label className="opt"><input type="checkbox" checked={data.upi_enabled} onChange={e => save({ upi_enabled: e.target.checked }, e.target.checked ? "Direct UPI is on." : "Direct UPI is off.")} /> <strong>Direct UPI</strong> to my UPI id (I confirm each payment)</label>
        <form className="form" onSubmit={(e: FormEvent) => { e.preventDefault(); save({ upi_id: upiId, upi_payee_name: payee }, "UPI details saved."); }}>
          <label>My UPI id<input value={upiId} onChange={e => setUpiId(e.target.value)} placeholder="yourname@okhdfcbank" maxLength={80} /></label>
          <label>Name shown in the UPI app<input value={payee} onChange={e => setPayee(e.target.value)} maxLength={80} /></label>
          <button className="solid">Save UPI details</button>
        </form>
        <p className="muted">With direct UPI the student pays your UPI id and enters the 12-digit UTR number. You check your bank or UPI app and press Confirm in the Payments tab. Nothing unlocks before you confirm.</p>
      </>)}
      {msg && <p role="status">{msg}</p>}
    </div>
  );
}

/** Send an update to every student: a changed course, a new feature, anything. */
export function AnnouncementsTab() {
  const [f, setF] = useState({ title: "", message: "", link: "" });
  const [msg, setMsg] = useState<string | null>(null);
  async function send(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    if (!window.confirm("Send this notification to every student?")) return;
    try { const r = await http<Obj>("/admin/announcements", { method: "POST", body: f }); setMsg(`Sent to ${r.sent_to} students.`); setF({ title: "", message: "", link: "" }); }
    catch (er) { setMsg(errText(er)); }
  }
  return (
    <form className="form" onSubmit={send} style={{ maxWidth: 560 }}>
      <h3>Send an update to all students</h3>
      <p className="muted">New courses and new challenges notify students automatically when you publish them. Use this for anything else, for example an updated course or a new feature.</p>
      <label>Title<input required minLength={3} maxLength={140} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder="Python course updated" /></label>
      <label>Message<textarea className="editor" rows={3} maxLength={1000} value={f.message} onChange={e => setF({ ...f, message: e.target.value })} /></label>
      <label>Open this page when tapped (optional)<input maxLength={200} value={f.link} onChange={e => setF({ ...f, link: e.target.value })} placeholder="/courses/python" /></label>
      <button className="solid">Send to all students</button>
      {msg && <p role="status">{msg}</p>}
    </form>
  );
}

/** Students who finished a course and are waiting for payment or for the admin. */
export function CertificateRequests({ onChange }: { onChange: () => void }) {
  const { data, err, load } = useLoad<Obj>("/admin/certificate-requests");
  const [msg, setMsg] = useState<string | null>(null);
  async function unlock(r: Obj, send_email: boolean) {
    const text = r.paid ? `Unlock the certificate for ${r.student}?` : `${r.student} has NOT paid. Unlock the certificate anyway?`;
    if (!window.confirm(text)) return;
    setMsg(null);
    try {
      const out = await http<Obj>("/admin/certificate-unlock", { method: "POST", body: { user_id: r.user_id, course_id: r.course_id, send_email } });
      setMsg(out.emailed ? `Unlocked and emailed to ${r.email}.` : out.email_error ? `Unlocked. Email not sent: ${out.email_error}` : "Unlocked. The student can now download it.");
      load(); onChange();
    } catch (e) { setMsg(errText(e)); }
  }
  return (
    <>
      <h3>Waiting for unlock</h3>
      <Err e={err} />
      <p className="muted">Students who finished a course but have no certificate yet. Mode: {data?.release_mode === "admin" ? "you unlock each certificate" : "automatic after payment"}.</p>
      {msg && <p role="status">{msg}</p>}
      {data && data.items.length === 0 && <p>Nobody is waiting.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table><thead><tr><th>Student</th><th>Email</th><th>Course</th><th>Project</th><th>Paid</th><th></th></tr></thead>
          <tbody>{data.items.map((r: Obj) => (
            <tr key={`${r.user_id}-${r.course_id}`}><td>{r.student}</td><td>{r.email}</td><td>{r.course}</td><td>{r.project_approved ? "Approved" : "Not approved"}</td><td>{r.paid ? "Yes" : "No"}</td>
              <td><button className="solid" onClick={() => unlock(r, false)}>Unlock</button>{" "}
                {data.email_configured && <button className="ghost" onClick={() => unlock(r, true)}>Unlock and email</button>}</td></tr>))}</tbody></table></div>
      )}
    </>
  );
}

/** Edit the details of a course (title, level, category, summary, objectives, time). */
export function CourseEditForm({ course, cats, onDone, onCancel }: { course: Obj; cats: Category[]; onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState({ title: course.title, category_id: course.category_id, level: course.level, summary: course.summary ?? "",
    objectives: (course.objectives ?? []).join("\n"), est_minutes: String(course.est_minutes ?? 0),
    is_paid: course.is_paid !== false, price_inr: course.price_inr ? String(course.price_inr) : "", project_title: course.project_title ?? "", project_description: course.project_description ?? "" });
  const [msg, setMsg] = useState<string | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      await http(`/admin/courses/${course.id}`, { method: "PATCH", body: { title: f.title, category_id: f.category_id, level: f.level, summary: f.summary,
        objectives: f.objectives.split("\n").map((s: string) => s.trim()).filter(Boolean), est_minutes: Number(f.est_minutes) || 0,
        is_paid: f.is_paid, price_inr: f.is_paid && f.price_inr ? Number(f.price_inr) : null, project_title: f.project_title.trim(), project_description: f.project_description.trim() } });
      onDone();
    } catch (er) { setMsg(errText(er)); }
  }
  return (
    <form className="form" onSubmit={save} style={{ maxWidth: 560 }}>
      <h3>Edit course</h3>
      <label>Title<input required minLength={2} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} /></label>
      <label>Category<select value={f.category_id} onChange={e => setF({ ...f, category_id: e.target.value })}>{cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Level<select value={f.level} onChange={e => setF({ ...f, level: e.target.value })}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
      <label>Summary<textarea className="editor" rows={3} value={f.summary} onChange={e => setF({ ...f, summary: e.target.value })} /></label>
      <label>What students will learn (one per line)<textarea className="editor" rows={4} value={f.objectives} onChange={e => setF({ ...f, objectives: e.target.value })} /></label>
      <label>Estimated minutes<input type="number" min={0} max={6000} value={f.est_minutes} onChange={e => setF({ ...f, est_minutes: e.target.value })} /></label>
      <h4>Price</h4>
      <label>Certificate<select value={f.is_paid ? "paid" : "free"} onChange={e => setF({ ...f, is_paid: e.target.value === "paid" })}><option value="paid">Paid</option><option value="free">Free</option></select></label>
      {f.is_paid && <label>Price in rupees (empty = the default price from Settings)<input type="number" min={1} max={100000} value={f.price_inr} onChange={e => setF({ ...f, price_inr: e.target.value })} /></label>}
      <h4>Project for this course</h4>
      <label>Project name (students submit this project)<input maxLength={160} value={f.project_title} onChange={e => setF({ ...f, project_title: e.target.value })} placeholder="Build a portfolio page" /></label>
      <label>Project description<textarea className="editor" rows={4} maxLength={3000} value={f.project_description} onChange={e => setF({ ...f, project_description: e.target.value })} /></label>
      <div className="row"><button className="solid">Save course</button><button type="button" className="ghost" onClick={onCancel}>Cancel</button></div>
      {msg && <p role="alert" className="err">{msg}</p>}
    </form>
  );
}

const LANGS = ["python", "java", "c", "cpp"];
const blankChallenge = () => ({ slug: "", title: "", language: "python", difficulty: "easy", topic: "", statement_md: "", input_format: "", output_format: "",
  constraints: "", starter_code: "", hints: "", explanation: "", tests: [{ stdin: "", expected: "", hidden: false }], published: true });

/** Coding challenges: list, add, edit (all fields and test cases), publish, delete. */
export function ChallengesManager() {
  const { data, err, load } = useLoad<{ items: Obj[] }>("/admin/challenges");
  const [form, setForm] = useState<Obj | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function edit(slug: string) {
    try {
      const c = await http<Obj>(`/admin/challenges/${slug}`);
      setForm({ ...c, hints: (c.hints ?? []).join("\n") }); setEditing(slug); setMsg(null);
    } catch (e) { setMsg(errText(e)); }
  }
  async function remove(c: Obj) {
    if (!window.confirm(`Delete the challenge "${c.title}"? Student submissions are kept but no longer linked.`)) return;
    await http(`/admin/challenges/${c.slug}`, { method: "DELETE" }).catch(e => setMsg(errText(e)));
    load();
  }
  async function toggle(c: Obj) {
    await http(`/admin/challenges/${c.slug}`, { method: "PATCH", body: { published: !c.published } }).catch(e => setMsg(errText(e)));
    load();
  }
  async function save(e: FormEvent) {
    e.preventDefault(); if (!form) return; setMsg(null);
    const body = { ...form, hints: String(form.hints).split("\n").map((s: string) => s.trim()).filter(Boolean) };
    try {
      if (editing) await http(`/admin/challenges/${editing}`, { method: "PUT", body });
      else await http("/admin/challenges", { method: "POST", body });
      setForm(null); setEditing(null); setMsg("Challenge saved."); load();
    } catch (er) { setMsg(errText(er)); }
  }
  const set = (k: string, v: any) => setForm(f => ({ ...f!, [k]: v }));
  const setTest = (i: number, k: string, v: any) => setForm(f => ({ ...f!, tests: f!.tests.map((t: Obj, j: number) => (j === i ? { ...t, [k]: v } : t)) }));

  if (form) {
    return (
      <form className="form" onSubmit={save} style={{ maxWidth: 640 }}>
        <h3>{editing ? `Edit challenge: ${editing}` : "New coding challenge"}</h3>
        <label>Slug (lowercase, dashes){editing ? " - cannot change" : ""}<input required disabled={!!editing} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} onChange={e => set("slug", e.target.value)} /></label>
        <label>Title<input required minLength={2} value={form.title} onChange={e => set("title", e.target.value)} /></label>
        <div className="row">
          <label>Language<select value={form.language} onChange={e => set("language", e.target.value)}>{LANGS.map(l => <option key={l}>{l}</option>)}</select></label>
          <label>Difficulty<select value={form.difficulty} onChange={e => set("difficulty", e.target.value)}><option>easy</option><option>medium</option><option>hard</option></select></label>
          <label>Topic<input value={form.topic} onChange={e => set("topic", e.target.value)} /></label>
        </div>
        <label>Problem statement (Markdown)<textarea className="editor" rows={5} value={form.statement_md} onChange={e => set("statement_md", e.target.value)} /></label>
        <label>Input format<input value={form.input_format} onChange={e => set("input_format", e.target.value)} /></label>
        <label>Output format<input value={form.output_format} onChange={e => set("output_format", e.target.value)} /></label>
        <label>Constraints<input value={form.constraints} onChange={e => set("constraints", e.target.value)} /></label>
        <label>Starter code<textarea className="editor" rows={4} value={form.starter_code} onChange={e => set("starter_code", e.target.value)} /></label>
        <label>Hints (one per line)<textarea className="editor" rows={3} value={form.hints} onChange={e => set("hints", e.target.value)} /></label>
        <label>Explanation shown after solving<textarea className="editor" rows={3} value={form.explanation} onChange={e => set("explanation", e.target.value)} /></label>
        <h4>Test cases</h4>
        {form.tests.map((t: Obj, i: number) => (
          <div key={i} className="card">
            <label>Input (stdin)<textarea className="editor" rows={2} value={t.stdin} onChange={e => setTest(i, "stdin", e.target.value)} /></label>
            <label>Expected output<textarea className="editor" rows={2} required value={t.expected} onChange={e => setTest(i, "expected", e.target.value)} /></label>
            <label className="opt"><input type="checkbox" checked={t.hidden} onChange={e => setTest(i, "hidden", e.target.checked)} /> Hidden test (students do not see it)</label>
            {form.tests.length > 1 && <button type="button" className="ghost" onClick={() => set("tests", form.tests.filter((_: Obj, j: number) => j !== i))}>Remove test</button>}
          </div>
        ))}
        <button type="button" className="ghost" onClick={() => set("tests", [...form.tests, { stdin: "", expected: "", hidden: false }])}>Add test case</button>
        <label className="opt"><input type="checkbox" checked={form.published} onChange={e => set("published", e.target.checked)} /> Published</label>
        <div className="row"><button className="solid">Save challenge</button><button type="button" className="ghost" onClick={() => { setForm(null); setEditing(null); }}>Cancel</button></div>
        {msg && <p role="alert" className="err">{msg}</p>}
      </form>
    );
  }
  return (
    <>
      <Err e={err} />
      {msg && <p role="status">{msg}</p>}
      <div className="row"><button className="solid" onClick={() => { setForm(blankChallenge()); setEditing(null); setMsg(null); }}>Add challenge</button></div>
      {data && data.items.length === 0 && <p>No challenges yet.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table><thead><tr><th>Title</th><th>Language</th><th>Level</th><th>Topic</th><th>Tests</th><th>Status</th><th></th></tr></thead>
          <tbody>{data.items.map(c => (
            <tr key={c.slug}><td>{c.title}</td><td>{c.language}</td><td>{c.difficulty}</td><td>{c.topic}</td><td>{c.tests}</td><td>{c.published ? "published" : "draft"}</td>
              <td><button className="ghost" onClick={() => edit(c.slug)}>Edit</button>{" "}<button className="ghost" onClick={() => toggle(c)}>{c.published ? "Unpublish" : "Publish"}</button>{" "}
                <button className="ghost" onClick={() => remove(c)}>Delete</button></td></tr>))}</tbody></table></div>
      )}
    </>
  );
}

/** Guided projects: add, edit, hide, delete. */
export function ProjectsManager() {
  const { data, err, load } = useLoad<{ items: Obj[] }>("/admin/projects");
  const [form, setForm] = useState<Obj | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function save(e: FormEvent) {
    e.preventDefault(); if (!form) return; setMsg(null);
    try {
      if (form.id) await http(`/admin/projects/${form.id}`, { method: "PATCH", body: { title: form.title, level: form.level, summary: form.summary, body_md: form.body_md, published: form.published } });
      else await http("/admin/projects", { method: "POST", body: form });
      setForm(null); setMsg("Project saved."); load();
    } catch (er) { setMsg(errText(er)); }
  }
  async function remove(p: Obj) {
    if (!window.confirm(`Delete the project "${p.title}"?`)) return;
    await http(`/admin/projects/${p.id}`, { method: "DELETE" }).catch(e => setMsg(errText(e)));
    load();
  }
  async function toggle(p: Obj) {
    await http(`/admin/projects/${p.id}`, { method: "PATCH", body: { published: !p.published } }).catch(e => setMsg(errText(e)));
    load();
  }
  const set = (k: string, v: any) => setForm(f => ({ ...f!, [k]: v }));
  if (form) {
    return (
      <form className="form" onSubmit={save} style={{ maxWidth: 640 }}>
        <h3>{form.id ? "Edit project" : "New project"}</h3>
        <label>Slug (lowercase, dashes){form.id ? " - cannot change" : ""}<input required disabled={!!form.id} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} onChange={e => set("slug", e.target.value)} /></label>
        <label>Title<input required minLength={2} value={form.title} onChange={e => set("title", e.target.value)} /></label>
        <label>Level<select value={form.level} onChange={e => set("level", e.target.value)}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
        <label>Short summary<input value={form.summary} onChange={e => set("summary", e.target.value)} /></label>
        <label>Steps and instructions (Markdown)<textarea className="editor" rows={10} value={form.body_md} onChange={e => set("body_md", e.target.value)} /></label>
        <label className="opt"><input type="checkbox" checked={form.published} onChange={e => set("published", e.target.checked)} /> Visible to students</label>
        <div className="row"><button className="solid">Save project</button><button type="button" className="ghost" onClick={() => setForm(null)}>Cancel</button></div>
        {msg && <p role="alert" className="err">{msg}</p>}
      </form>
    );
  }
  return (
    <>
      <Err e={err} />
      {msg && <p role="status">{msg}</p>}
      <div className="row"><button className="solid" onClick={() => { setForm({ slug: "", title: "", level: "beginner", summary: "", body_md: "", published: true }); setMsg(null); }}>Add project</button></div>
      {data && data.items.length === 0 && <p>No projects yet.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table><thead><tr><th>Title</th><th>Level</th><th>Steps written</th><th>Visible</th><th></th></tr></thead>
          <tbody>{data.items.map(p => (
            <tr key={p.id}><td>{p.title}</td><td>{p.level}</td><td>{p.body_md.trim() ? "Yes" : "No (shows as planned)"}</td><td>{p.published ? "Yes" : "No"}</td>
              <td><button className="ghost" onClick={() => setForm({ ...p })}>Edit</button>{" "}<button className="ghost" onClick={() => toggle(p)}>{p.published ? "Hide" : "Show"}</button>{" "}
                <button className="ghost" onClick={() => remove(p)}>Delete</button></td></tr>))}</tbody></table></div>
      )}
    </>
  );
}


const STATUS: Record<string, string> = { submitted: "Waiting for review", approved: "Approved", changes_requested: "Changes requested" };

/** Student projects: read them, then approve (optionally unlocking the certificate now) or ask for changes. */
export function SubmissionsTab() {
  const [filter, setFilter] = useState("submitted");
  const { data, err, load } = useLoad<{ items: Obj[] }>(`/admin/project-submissions${filter ? `?status=${filter}` : ""}`);
  const [open, setOpen] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");
  const [email, setEmail] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function review(s: Obj, decision: "approved" | "changes_requested", release = false) {
    if (release && !window.confirm(`Approve and unlock the certificate for ${s.student} now? This skips the payment.`)) return;
    setMsg(null);
    try {
      const out = await http<Obj>(`/admin/project-submissions/${s.id}/review`, { method: "PATCH", body: { decision, feedback, release, send_email: email } });
      setMsg(`${decision === "approved" ? (out.certificate_issued ? "Approved. Certificate issued." : "Approved. The student can now pay for the certificate.") : "Sent back to the student for changes."}${out.emailed ? " Email sent." : out.email_error ? ` Email not sent: ${out.email_error}` : ""}`);
      setOpen(null); setFeedback(""); load();
    } catch (e) { setMsg(errText(e)); }
  }
  return (
    <>
      <div className="row" style={{ marginTop: 0 }}>
        <label>Show<select value={filter} onChange={e => { setFilter(e.target.value); setOpen(null); }}>
          <option value="submitted">Waiting for review</option><option value="changes_requested">Changes requested</option><option value="approved">Approved</option><option value="">All</option></select></label>
      </div>
      <Err e={err} />
      {msg && <p role="status">{msg}</p>}
      {data && data.items.length === 0 && <p>No submissions here.</p>}
      <div className="stack">
        {data?.items.map(s => (
          <div key={s.id} className="card">
            <div className="row" style={{ marginTop: 0, justifyContent: "space-between" }}>
              <div><h3>{s.title}</h3><p className="muted">{s.student} · {s.email}{s.college_name ? ` · ${s.college_name}` : ""} · {s.course}</p></div>
              <span className={`status ${s.status}`}>{STATUS[s.status]}</span>
            </div>
            {open === s.id ? (
              <>
                <p style={{ whiteSpace: "pre-wrap" }}>{s.description}</p>
                <p className="links">{s.repo_url && <a href={s.repo_url} target="_blank" rel="noopener noreferrer">Source code</a>}{s.demo_url && <a href={s.demo_url} target="_blank" rel="noopener noreferrer">Live demo</a>}</p>
                <p className="muted">Submitted {new Date(s.submitted_at).toLocaleString()} · Payment: {s.paid ? "received" : "not yet"} · Certificate: {s.certificate_issued ? "issued" : "not issued"}</p>
                <label>Feedback to the student{s.status === "changes_requested" ? "" : " (required only when asking for changes)"}<textarea className="editor" rows={3} maxLength={2000} value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="What is good, and what must change?" /></label>
                <label className="opt"><input type="checkbox" checked={email} onChange={e => setEmail(e.target.checked)} /> Also email the student (needs email set up)</label>
                <div className="row">
                  <button className="solid" onClick={() => review(s, "approved")}>Approve</button>
                  {!s.certificate_issued && <button className="ghost" onClick={() => review(s, "approved", true)}>Approve and unlock certificate now</button>}
                  <button className="ghost" onClick={() => review(s, "changes_requested")}>Request changes</button>
                  <button className="ghost" onClick={() => setOpen(null)}>Close</button>
                </div>
              </>
            ) : <button className="ghost" onClick={() => { setOpen(s.id); setFeedback(s.admin_feedback || ""); setMsg(null); }}>Open and review</button>}
          </div>
        ))}
      </div>
    </>
  );
}

/** Admin edits every detail of a student. */
export function StudentEditor({ student, onSaved }: { student: Obj; onSaved: () => void }) {
  const [f, setF] = useState<Obj>({ ...student.profile });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => setF({ ...student.profile }), [student]);
  const set = (k: string) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setMsg(null); };
  async function save(e: FormEvent) {
    e.preventDefault();
    try { await http(`/admin/students/${student.id}/profile`, { method: "PUT", body: f }); setMsg({ ok: true, text: "Student details saved." }); onSaved(); }
    catch (er) { setMsg({ ok: false, text: errText(er) }); }
  }
  const field = (k: string, label: string, type = "text") => <label>{label}<input type={type} value={f[k] ?? ""} onChange={set(k)} /></label>;
  return (
    <form className="card form-grid" onSubmit={save} style={{ maxWidth: 640 }}>
      <h3>Student details (editable)</h3>
      {field("display_name", "Full name (printed on the certificate)")}
      {field("email", "Email", "email")}
      {field("phone", "Phone number", "tel")}
      {field("college_name", "College name")}
      {field("degree", "Degree and department")}
      {field("year_of_study", "Year of study")}
      {field("school_name", "School name")}
      {field("tenth_mark", "10th mark")}
      {field("twelfth_mark", "12th mark")}
      {field("city", "City")}
      <div className="row"><button className="solid">Save student details</button></div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "ok" : "err"}>{msg.text}</p>}
    </form>
  );
}


/** Final exam results are hidden from students. The admin sees every submission here and releases each result. */
export function FinalResultsTab() {
  const { data, err, load } = useLoad<Obj>("/admin/final-results");
  const [msg, setMsg] = useState<string | null>(null);
  async function release(id: number) {
    setMsg(null);
    try { await http(`/admin/final-results/${id}/release`, { method: "POST" }); setMsg("Result released. The student can now see it and continue to payment."); load(); }
    catch (e) { setMsg(errText(e)); }
  }
  const items: Obj[] = data?.items ?? [];
  return (
    <>
      <Err e={err} />
      <p className="muted">Students do not see marks after the final exam. Release a result to show it to the student; if they passed, they can then press Next and pay.</p>
      {msg && <p role="status">{msg}</p>}
      {data && items.length === 0 && <p>No final exam has been submitted yet.</p>}
      {items.length > 0 && (
        <div className="scroll"><table>
          <thead><tr><th>Student</th><th>Email</th><th>Course</th><th>Score</th><th>Result</th><th>Submitted</th><th></th></tr></thead>
          <tbody>{items.map(i => (
            <tr key={i.attempt_id}><td>{i.student}</td><td>{i.email}</td><td>{i.course}</td><td>{i.score_pct}%</td>
              <td>{i.passed ? "Passed" : "Not passed"} (pass {i.pass_mark}%)</td><td>{i.submitted_at ? new Date(i.submitted_at).toLocaleString() : ""}</td>
              <td>{i.released ? <span className="ok">Released</span> : <button className="solid" onClick={() => release(i.attempt_id)}>Release result</button>}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}
