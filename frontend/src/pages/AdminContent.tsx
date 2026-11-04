import { FormEvent, useCallback, useEffect, useState } from "react";
import { errText, http } from "../api";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;
const LABELS = "abcdefgh";
const KIND_LABEL: Record<string, string> = { chapter: "Topic test", final: "Final exam", practice: "Practice" };

function useLoad<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { if (!path) return; setErr(null); http<T>(path).then(setData).catch(e => setErr(errText(e))); }, [path]);
  useEffect(load, [load]);
  return { data, err, load };
}
const Err = ({ e }: { e: string | null }) => (e ? <p role="alert" className="err">{e}</p> : null);

/** One test question: single choice, multiple choice or short answer. Pass `initial` to edit an existing question. */
export function QuestionForm({ onSubmit, label, initial, onCancel }: { onSubmit: (q: Obj) => Promise<void> | void; label: string; initial?: Obj; onCancel?: () => void }) {
  const isShort = initial?.qtype === "short";
  const [qtype, setQtype] = useState<string>(initial?.qtype ?? "single");
  const [prompt, setPrompt] = useState<string>(initial?.prompt ?? "");
  const [opts, setOpts] = useState<string[]>(initial && !isShort ? [...initial.options.map((o: Obj) => o.text), ...["", "", "", ""]].slice(0, Math.max(4, initial.options.length)) : ["", "", "", ""]);
  const [correct, setCorrect] = useState<number[]>(initial && !isShort ? initial.options.flatMap((o: Obj, i: number) => (initial.answer.includes(o.id) ? [i] : [])) : []);
  const [accepted, setAccepted] = useState<string>(isShort ? initial!.answer.join(", ") : "");
  const [expl, setExpl] = useState<string>(initial?.explanation ?? "");
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault(); setErr(null);
    let payload: Obj;
    if (qtype === "short") {
      const answers = accepted.split(",").map(s => s.trim()).filter(Boolean);
      if (!answers.length) return setErr("Enter at least one accepted answer (separate several with commas).");
      payload = { qtype, prompt, options: [], answer: answers, explanation: expl };
    } else {
      const kept = opts.map((t, i) => ({ t: t.trim(), i })).filter(o => o.t);
      if (kept.length < 2) return setErr("Enter at least two options.");
      const answer = kept.flatMap((o, idx) => (correct.includes(o.i) ? [LABELS[idx]] : []));
      if (qtype === "single" && answer.length !== 1) return setErr("Mark exactly one correct option.");
      if (!answer.length) return setErr("Mark at least one correct option.");
      payload = { qtype, prompt, options: kept.map((o, idx) => ({ id: LABELS[idx], text: o.t })), answer, explanation: expl };
    }
    try {
      await onSubmit(payload);
      if (!initial) { setPrompt(""); setOpts(["", "", "", ""]); setCorrect([]); setAccepted(""); setExpl(""); }
    } catch (er) { setErr(errText(er)); }
  }
  const mark = (i: number, on: boolean) => setCorrect(c => (qtype === "single" ? [i] : on ? [...c, i] : c.filter(x => x !== i)));

  return (
    <form className="card form" onSubmit={submit} style={{ maxWidth: 640 }}>
      <label>Question type
        <select value={qtype} onChange={e => { setQtype(e.target.value); setCorrect([]); }}>
          <option value="single">Single choice</option><option value="multiple">Multiple choice (several correct)</option><option value="short">Short answer</option>
        </select>
      </label>
      <label>Question<textarea className="editor" rows={2} required minLength={3} maxLength={2000} value={prompt} onChange={e => setPrompt(e.target.value)} /></label>
      {qtype === "short" ? (
        <label>Accepted answers (comma separated, not case sensitive)<input value={accepted} onChange={e => setAccepted(e.target.value)} /></label>
      ) : (
        <fieldset className="q"><legend>Options (tick the correct {qtype === "single" ? "one" : "ones"})</legend>
          {opts.map((t, i) => (
            <div key={i} className="opt">
              <input type={qtype === "single" ? "radio" : "checkbox"} name="correct" aria-label={`Option ${i + 1} is correct`}
                checked={correct.includes(i)} onChange={e => mark(i, e.target.checked)} />
              <input style={{ flex: 1 }} placeholder={`Option ${i + 1}`} maxLength={300} value={t} onChange={e => setOpts(o => o.map((x, j) => (j === i ? e.target.value : x)))} />
            </div>
          ))}
          {opts.length < 8 && <button type="button" className="ghost" onClick={() => setOpts(o => [...o, ""])}>Add option</button>}
        </fieldset>
      )}
      <label>Explanation shown after the quiz (optional)<textarea className="editor" rows={2} maxLength={2000} value={expl} onChange={e => setExpl(e.target.value)} /></label>
      <Err e={err} />
      <div className="row"><button className="solid">{label}</button>{onCancel && <button type="button" className="ghost" onClick={onCancel}>Cancel</button>}</div>
    </form>
  );
}

function LessonForm({ modules, editId, onDone }: { modules: Obj[]; editId: number | null; onDone: () => void }) {
  const blank = { module_id: modules[0]?.id ?? 0, slug: "", title: "", body_md: "", example_lang: "python", example_code: "", expected_output: "", published: false };
  const [f, setF] = useState<Obj>(blank);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    setMsg(null);
    if (editId) http<Obj>(`/admin/lessons/${editId}`).then(l => setF({ ...blank, ...l })).catch(e => setMsg({ ok: false, text: errText(e) }));
    else setF({ ...blank, module_id: modules[0]?.id ?? 0 });
  }, [editId, modules.length]);  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: string, v: any) => setF(x => ({ ...x, [k]: v }));

  async function save(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      if (editId) {
        const { title, body_md, example_code, example_lang, expected_output, published } = f;
        await http(`/admin/lessons/${editId}`, { method: "PATCH", body: { title, body_md, example_code, example_lang, expected_output, published } });
      } else {
        await http("/admin/lessons", { method: "POST", body: { ...f, module_id: Number(f.module_id) } });
        setF({ ...blank, module_id: f.module_id });
      }
      setMsg({ ok: true, text: editId ? "Lesson saved." : "Lesson added." });
      onDone();
    } catch (er) { setMsg({ ok: false, text: errText(er) }); }
  }
  return (
    <form className="card form" onSubmit={save} style={{ maxWidth: 720 }}>
      <h3>{editId ? "Edit lesson" : "Add a lesson"}</h3>
      {!editId && (<>
        <label>Module<select value={f.module_id} onChange={e => set("module_id", e.target.value)}>{modules.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}</select></label>
        <label>Slug (lowercase, dashes, used in the lesson address)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" minLength={2} value={f.slug} onChange={e => set("slug", e.target.value)} /></label>
      </>)}
      <label>Title<input required minLength={2} maxLength={160} value={f.title} onChange={e => set("title", e.target.value)} /></label>
      <label>Lesson text (Markdown: ## headings, lists, `code`)<textarea className="editor" rows={12} maxLength={50000} value={f.body_md} onChange={e => set("body_md", e.target.value)} /></label>
      <label>Example language
        <select value={f.example_lang} onChange={e => set("example_lang", e.target.value)}>{["python", "java", "c", "cpp", "html", "css", "javascript"].map(l => <option key={l}>{l}</option>)}</select></label>
      <label>Example code<textarea className="editor" rows={6} maxLength={10000} value={f.example_code} onChange={e => set("example_code", e.target.value)} /></label>
      <label>Expected output (optional)<textarea className="editor" rows={3} maxLength={5000} value={f.expected_output} onChange={e => set("expected_output", e.target.value)} /></label>
      <label className="opt"><input type="checkbox" checked={!!f.published} onChange={e => set("published", e.target.checked)} /> Published (students can see it)</label>
      {msg && <p role="status" className={msg.ok ? "" : "err"}>{msg.text}</p>}
      <div className="row"><button className="solid">{editId ? "Save changes" : "Add lesson"}</button></div>
    </form>
  );
}

export function CourseManager({ courseId, onBack }: { courseId: number; onBack: () => void }) {
  const { data, err, load } = useLoad<Obj>(`/admin/courses/${courseId}`);
  const allQuizzes = useLoad<{ items: Obj[] }>("/admin/quizzes");
  const [editId, setEditId] = useState<number | null>(null);
  const [openQuiz, setOpenQuiz] = useState<number | null>(null);
  const [mod, setMod] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function addModule(e: FormEvent) {
    e.preventDefault();
    try { await http("/admin/modules", { method: "POST", body: { course_id: courseId, title: mod } }); setMod(""); load(); }
    catch (er) { setMsg(errText(er)); }
  }
  async function toggle(l: Obj) {
    if (!window.confirm(`${l.published ? "Unpublish" : "Publish"} "${l.title}"? Student progress is kept.`)) return;
    await http(`/admin/lessons/${l.id}`, { method: "PATCH", body: { published: !l.published } }).catch(er => setMsg(errText(er)));
    load();
  }
  async function removeLesson(l: Obj) {
    if (!window.confirm(`Delete the lesson "${l.title}"? Students' progress on it is removed. Use Unpublish to only hide it.`)) return;
    await http(`/admin/lessons/${l.id}`, { method: "DELETE" }).catch(er => setMsg(errText(er)));
    load();
  }
  async function renameModule(m: Obj) {
    const title = window.prompt("New module title", m.title);
    if (!title || title.trim().length < 2) return;
    await http(`/admin/modules/${m.id}`, { method: "PATCH", body: { title: title.trim() } }).catch(er => setMsg(errText(er)));
    load();
  }
  async function removeModule(m: Obj) {
    if (!window.confirm(`Delete the module "${m.title}" with all ${m.lessons.length} of its lessons?`)) return;
    await http(`/admin/modules/${m.id}`, { method: "DELETE" }).catch(er => setMsg(errText(er)));
    load();
  }
  async function removeQuiz(q: Obj) {
    if (!window.confirm(`Delete "${q.title}" with its questions and all student attempts?`)) return;
    await http(`/admin/quizzes/${q.id}`, { method: "DELETE" }).catch(er => setMsg(errText(er)));
    allQuizzes.load();
  }
  if (openQuiz) return <QuizDetail id={openQuiz} onBack={() => { setOpenQuiz(null); allQuizzes.load(); }} />;
  const quizzes = allQuizzes.data?.items.filter(q => data && q.course_slug === data.slug) ?? [];
  return (
    <>
      <button className="ghost" onClick={onBack}>Back to courses</button>
      <Err e={err} />
      {data && (<>
        <h2>{data.title} {data.published ? "" : <span className="tag">draft</span>}</h2>
        <h3>Topics and lessons</h3>
        {data.modules.length === 0 && <p>No modules yet. Add a module first, then add lessons to it.</p>}
        {data.modules.map((m: Obj) => (
          <div key={m.id}><h4>{m.title} <button className="ghost" onClick={() => renameModule(m)}>Rename</button> <button className="ghost" onClick={() => removeModule(m)}>Delete module</button></h4>
            {m.lessons.length === 0 ? <p className="muted">No lessons in this module.</p> : (
              <ul className="plain">{m.lessons.map((l: Obj) => (
                <li key={l.id}>{l.title} <span className="tag">{l.published ? "published" : "draft"}</span>{" "}
                  <button className="ghost" onClick={() => setEditId(l.id)}>Edit</button>{" "}
                  <button className="ghost" onClick={() => toggle(l)}>{l.published ? "Unpublish" : "Publish"}</button>{" "}
                  <button className="ghost" onClick={() => removeLesson(l)}>Delete</button></li>))}</ul>)}
          </div>
        ))}
        <form className="form" onSubmit={addModule} style={{ maxWidth: 420 }}>
          <label>New module title<input required minLength={2} maxLength={120} value={mod} onChange={e => setMod(e.target.value)} /></label>
          <button className="ghost">Add module</button>
        </form>
        {msg && <p role="alert" className="err">{msg}</p>}
        {data.modules.length > 0 && <LessonForm modules={data.modules} editId={editId} onDone={load} />}
        {editId && <button className="ghost" onClick={() => setEditId(null)}>Stop editing and add a new lesson</button>}

        <h3>Topic tests, practice and final exam of this course</h3>
        {quizzes.length === 0 ? <p>None yet. Create them in the Quizzes tab.</p> : (
          <ul className="plain">{quizzes.map(q => (
            <li key={q.id}><strong>{KIND_LABEL[q.kind]}:</strong> {q.title} <span className="tag">{q.question_count} questions</span> <span className="tag">{q.published ? "published" : "draft"}</span>{" "}
              <button className="ghost" onClick={() => setOpenQuiz(q.id)}>View and edit questions</button>{" "}<button className="ghost" onClick={() => removeQuiz(q)}>Delete</button></li>))}</ul>)}
        <p className="muted">A course appears to students once it is published and has at least one published lesson. Unpublish hides a lesson and keeps student progress; Delete removes it and the progress on it.</p>
      </>)}
    </>
  );
}

function QuizDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const { data, err, load } = useLoad<Obj>(`/admin/quizzes/${id}`);
  const [editing, setEditing] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function remove(q: Obj) {
    if (!window.confirm("Delete this question? Past attempts keep their saved scores, but future attempts will no longer include it.")) return;
    try { await http(`/admin/questions/${q.id}`, { method: "DELETE" }); load(); } catch (e) { setMsg(errText(e)); }
  }
  return (
    <>
      <button className="ghost" onClick={onBack}>Back</button>
      <Err e={err} />
      {data && (<>
        <h2>{data.title}</h2><p className="muted">{KIND_LABEL[data.kind]} · pass mark {data.pass_mark}% · {data.published ? "published" : "draft"}</p>
        {msg && <p role="alert" className="err">{msg}</p>}
        {data.questions.length === 0 && <p>No questions yet.</p>}
        <ol>{data.questions.map((q: Obj) => (
          <li key={q.id}>
            {editing === q.id ? (
              <QuestionForm key={q.id} initial={q} label="Save changes" onCancel={() => setEditing(null)}
                onSubmit={async body => { await http(`/admin/questions/${q.id}`, { method: "PATCH", body }); setEditing(null); load(); }} />
            ) : (<>
              <p>{q.prompt} <span className="tag">{q.qtype}</span></p>
              {q.qtype === "short" ? <p className="muted">Accepted: {q.answer.join(" / ")}</p> :
                <ul className="plain">{q.options.map((o: Obj) => <li key={o.id}>{q.answer.includes(o.id) ? "✓ " : ""}{o.text}</li>)}</ul>}
              <button className="ghost" onClick={() => setEditing(q.id)}>Edit</button>{" "}
              <button className="ghost" onClick={() => remove(q)}>Delete</button></>)}
          </li>))}</ol>
        <h3>Add a question</h3>
        <QuestionForm label="Add question" onSubmit={async q => { await http(`/admin/quizzes/${id}/questions`, { method: "POST", body: q }); load(); }} />
      </>)}
    </>
  );
}

function QuizCreate({ onCreated }: { onCreated: () => void }) {
  const courses = useLoad<{ items: Obj[] }>("/admin/courses");
  const [f, setF] = useState<Obj>({ course_slug: "", title: "", kind: "chapter", pass_mark: 70, time_limit_minutes: "", published: false });
  const [qs, setQs] = useState<Obj[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { if (courses.data && !f.course_slug) setF((x: Obj) => ({ ...x, course_slug: courses.data!.items[0]?.slug ?? "" })); }, [courses.data]);  // eslint-disable-line react-hooks/exhaustive-deps
  async function create(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    if (!qs.length) return setMsg({ ok: false, text: "Add at least one question first." });
    try {
      await http("/admin/quizzes", { method: "POST", body: { ...f, pass_mark: Number(f.pass_mark), time_limit_minutes: f.time_limit_minutes === "" ? null : Number(f.time_limit_minutes), questions: qs } });
      setQs([]); setF({ ...f, title: "" }); setMsg({ ok: true, text: "Created." }); onCreated();
    } catch (er) { setMsg({ ok: false, text: errText(er) }); }
  }
  const set = (k: string, v: any) => setF((x: Obj) => ({ ...x, [k]: v }));
  return (
    <>
      <h3>Create a topic test, practice set or final exam</h3>
      <form className="card form" onSubmit={create} style={{ maxWidth: 640 }}>
        <label>Course<select value={f.course_slug} onChange={e => set("course_slug", e.target.value)}>{courses.data?.items.map(c => <option key={c.slug} value={c.slug}>{c.title}</option>)}</select></label>
        <label>Title (for a topic test, name the topic)<input required minLength={2} value={f.title} onChange={e => set("title", e.target.value)} /></label>
        <label>Type
          <select value={f.kind} onChange={e => set("kind", e.target.value)}>
            <option value="chapter">Topic test (must be attended before the final exam opens)</option>
            <option value="practice">Practice (free, optional, no XP)</option>
            <option value="final">Final exam (locked until all lessons and topic tests are done)</option>
          </select></label>
        <label>Pass mark (%)<input type="number" min={1} max={100} value={f.pass_mark} onChange={e => set("pass_mark", e.target.value)} /></label>
        <label>Time limit in minutes (leave empty for none)<input type="number" min={1} max={240} value={f.time_limit_minutes} onChange={e => set("time_limit_minutes", e.target.value)} /></label>
        <label className="opt"><input type="checkbox" checked={f.published} onChange={e => set("published", e.target.checked)} /> Publish immediately</label>
        <p><strong>{qs.length}</strong> question(s) added below.</p>
        {msg && <p role="status" className={msg.ok ? "" : "err"}>{msg.text}</p>}
        <button className="solid">Create</button>
      </form>
      <QuestionForm label="Add this question to the new set" onSubmit={q => { setQs(x => [...x, q]); }} />
      {qs.length > 0 && <ol className="plain">{qs.map((q, i) => <li key={i}>{q.prompt} <button className="ghost" onClick={() => setQs(x => x.filter((_, j) => j !== i))}>Remove</button></li>)}</ol>}
    </>
  );
}

export function QuizManager() {
  const { data, err, load } = useLoad<{ items: Obj[] }>("/admin/quizzes");
  const [open, setOpen] = useState<number | null>(null);
  async function toggle(q: Obj) {
    if (!window.confirm(`${q.published ? "Unpublish" : "Publish"} "${q.title}"?`)) return;
    await http(`/admin/quizzes/${q.id}`, { method: "PATCH", body: { published: !q.published } }).catch(() => undefined);
    load();
  }
  async function remove(q: Obj) {
    if (!window.confirm(`Delete "${q.title}" with its questions and all student attempts?`)) return;
    await http(`/admin/quizzes/${q.id}`, { method: "DELETE" }).catch(() => undefined);
    load();
  }
  if (open) return <QuizDetail id={open} onBack={() => { setOpen(null); load(); }} />;
  return (
    <>
      <Err e={err} />
      {data && data.items.length === 0 && <p>Nothing yet. Create one below.</p>}
      {data && data.items.length > 0 && (
        <div className="scroll"><table><thead><tr><th>Title</th><th>Course</th><th>Type</th><th>Questions</th><th>Status</th><th></th></tr></thead>
          <tbody>{data.items.map(q => <tr key={q.id}><td>{q.title}</td><td>{q.course}</td><td>{KIND_LABEL[q.kind]}</td><td>{q.question_count}</td><td>{q.published ? "published" : "draft"}</td>
            <td><button className="ghost" onClick={() => setOpen(q.id)}>Questions</button> <button className="ghost" onClick={() => toggle(q)}>{q.published ? "Unpublish" : "Publish"}</button> <button className="ghost" onClick={() => remove(q)}>Delete</button></td></tr>)}</tbody></table></div>
      )}
      <QuizCreate onCreated={load} />
    </>
  );
}
