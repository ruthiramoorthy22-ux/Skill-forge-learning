import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, http } from "../api";
import { useAuth } from "../auth";

interface Item { slug: string; title: string; language: string; difficulty: string; topic: string }
interface Detail extends Item {
  statement_md: string; input_format: string; output_format: string; constraints: string; starter_code: string;
  hints: string[]; examples: { input: string; output: string }[]; hidden_test_count: number;
}
interface Row { test: number; hidden: boolean; passed: boolean; status: string; input?: string; expected?: string; actual?: string; error?: string }
interface Outcome { status: string; passed: number; total: number; results: Row[]; new_achievements: string[] }

export function ChallengeList() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { http<{ items: Item[] }>("/challenges").then(r => setItems(r.items)).catch(() => setErr(true)); }, []);
  return (
    <section className="page">
      <h1>Coding challenges</h1>
      <p className="muted">Solutions are checked by running your code against test cases on a sandbox service. Challenges are Python for now.</p>
      {err && <p role="alert" className="err">Could not load challenges.</p>}
      {!items && !err && <p>Loading…</p>}
      <ul className="grid">{items?.map(c => (
        <li key={c.slug} className="card"><h3><Link to={`/challenges/${c.slug}`}>{c.title}</Link></h3>
          <p className="muted">{c.topic}</p><p><span className="tag">{c.difficulty}</span> <span className="tag">{c.language}</span></p></li>
      ))}</ul>
    </section>
  );
}

export function ChallengeDetail() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const [c, setC] = useState<Detail | null>(null);
  const [code, setCode] = useState("");
  const [hintsShown, setHintsShown] = useState(0);
  const [res, setRes] = useState<Outcome | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<{ id: number; status: string; passed: number; total: number }[]>([]);

  const loadHistory = () => { if (user) http<{ items: typeof history }>(`/challenges/${slug}/submissions`).then(r => setHistory(r.items)).catch(() => undefined); };
  useEffect(() => { http<Detail>(`/challenges/${slug}`).then(d => { setC(d); setCode(d.starter_code); }).catch(e => setErr(e.message)); }, [slug]);
  useEffect(loadHistory, [slug, user?.id]);

  async function submit() {
    if (!c) return;
    setBusy(true); setErr(null); setRes(null);
    try { setRes(await http<Outcome>(`/challenges/${slug}/submit`, { method: "POST", body: { language: c.language, source: code } })); loadHistory(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not submit."); }
    finally { setBusy(false); }
  }

  if (!c) return <section className="page">{err ? <p role="alert" className="err">{err}</p> : <p>Loading…</p>}</section>;
  return (
    <section className="page">
      <h1>{c.title}</h1>
      <p><span className="tag">{c.difficulty}</span> <span className="tag">{c.language}</span> <span className="tag">{c.topic}</span></p>
      <p>{c.statement_md}</p>
      <p><strong>Input:</strong> {c.input_format}</p>
      <p><strong>Output:</strong> {c.output_format}</p>
      <p><strong>Constraints:</strong> {c.constraints}</p>
      <h3>Examples</h3>
      {c.examples.map((e, i) => <pre key={i} className="example"><code>{`Input:  ${e.input}\nOutput: ${e.output}`}</code></pre>)}
      <p className="muted">{c.hidden_test_count} more tests are hidden.</p>
      {user ? (
        <>
          <label>Your solution
            <textarea className="editor" spellCheck={false} value={code} onChange={e => setCode(e.target.value)} rows={10} maxLength={20000} />
          </label>
          <div className="row">
            <button className="solid" onClick={submit} disabled={busy}>{busy ? "Checking…" : "Submit"}</button>
            <button className="ghost" onClick={() => setCode(c.starter_code)}>Reset code</button>
            {hintsShown < c.hints.length && <button className="ghost" onClick={() => setHintsShown(hintsShown + 1)}>Show a hint</button>}
          </div>
        </>
      ) : <p><Link to="/signin">Sign in</Link> to submit a solution.</p>}
      {c.hints.slice(0, hintsShown).map((h, i) => <p key={i} className="notice">Hint {i + 1}: {h}</p>)}
      {err && <p role="alert" className="err">{err}</p>}
      {res && (
        <div aria-live="polite">
          <h2>{res.status === "accepted" ? "Accepted" : res.status === "error" ? "Your code had errors" : "Some tests failed"} ({res.passed}/{res.total})</h2>
          {res.new_achievements.length > 0 && <p className="notice">Achievement unlocked: {res.new_achievements.join(", ")}</p>}
          <ul className="plain">{res.results.map(r => (
            <li key={r.test}>Test {r.test}{r.hidden ? " (hidden)" : ""}: {r.passed ? "passed" : "failed"}
              {!r.hidden && !r.passed && <pre className="example"><code>{`Input: ${r.input}\nExpected: ${r.expected}\nYour output: ${r.actual}\n${r.error ?? ""}`}</code></pre>}</li>
          ))}</ul>
        </div>
      )}
      {history.length > 0 && <><h3>Your submissions</h3><ul className="plain">{history.map(h => <li key={h.id}>{h.status}: {h.passed}/{h.total} tests</li>)}</ul></>}
    </section>
  );
}
