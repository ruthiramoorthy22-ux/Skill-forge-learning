import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, http } from "../api";

interface Q { id: number; qtype: "single" | "multiple" | "short"; prompt: string; options: { id: string; text: string }[] }
interface Started { attempt_id: number; kind?: string; title: string; pass_mark: number; time_limit_minutes: number | null; questions: Q[] }
interface Outcome {
  score_pct: number; passed: boolean; pass_mark: number; correct_count: number; total: number; new_achievements: string[];
  results: { question_id: number; correct: boolean; your_answer: string[]; correct_answer: string[]; explanation: string }[];
}

interface Pending { pending_review: true; message: string; course_slug: string }

export default function Quiz() {
  const { id = "" } = useParams();
  const [quiz, setQuiz] = useState<Started | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [res, setRes] = useState<Outcome | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [courseSlug, setCourseSlug] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const start = () => {
    setRes(null); setPending(null); setAnswers({}); setErr(null); setQuiz(null);
    http<Started>(`/quizzes/${id}/start`, { method: "POST" }).then(setQuiz).catch(e => setErr(e.message));
  };
  useEffect(start, [id]);

  async function submit() {
    if (!quiz) return;
    try {
      const out = await http<Outcome | Pending>(`/quizzes/${id}/submit`, { method: "POST", body: { attempt_id: quiz.attempt_id, answers } });
      if ("pending_review" in out) {  // final exam: no marks, no answers; the admin releases the result
        setPending(out.message);
        setCourseSlug(out.course_slug);
      } else setRes(out);
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not submit."); }
  }
  const pick = (q: Q, opt: string, checked: boolean) => setAnswers(a => {
    const cur = a[q.id] ?? [];
    return { ...a, [q.id]: q.qtype === "single" ? [opt] : checked ? [...cur, opt] : cur.filter(x => x !== opt) };
  });

  if (err && !quiz) return <section className="page"><p role="alert" className="err">{err}</p><Link to="/courses">Back to courses</Link></section>;
  if (!quiz) return <section className="page"><p>Loading…</p></section>;

  if (pending) {
    return (
      <section className="page narrow result-screen">
        <div className="result-card wait">
          <div className="big-ico" aria-hidden="true">📨</div>
          <h1>Final exam submitted</h1>
          <p>{pending}</p>
          <p className="muted">You will not see marks or answers now. Your result is sent to the admin first.</p>
          <div className="row">{courseSlug && <Link className="solid" to={`/courses/${courseSlug}/result`}>Check my result</Link>}<Link className="ghost" to="/home">Home</Link></div>
        </div>
      </section>
    );
  }
  if (res) {
    return (
      <section className="page">
        <h1>{quiz.title}: {res.score_pct}% {res.passed ? "(passed)" : "(not passed)"}</h1>
        <p>{res.correct_count} of {res.total} correct. Pass mark: {res.pass_mark}%.</p>
        {res.new_achievements.length > 0 && <p className="notice">Achievement unlocked: {res.new_achievements.join(", ")}</p>}
        <ol>{quiz.questions.map(q => {
          const r = res.results.find(x => x.question_id === q.id)!;
          return <li key={q.id}><p>{q.prompt}</p><p className={r.correct ? "" : "err"}>{r.correct ? "Correct." : `Incorrect. Correct answer: ${q.qtype === "short" ? r.correct_answer.join(" / ") : q.options.filter(o => r.correct_answer.includes(o.id)).map(o => o.text).join(", ")}`}</p><p className="muted">{r.explanation}</p></li>;
        })}</ol>
        <div className="row"><button className="solid" onClick={start}>Try again</button></div>
      </section>
    );
  }
  return (
    <section className="page">
      <h1>{quiz.title}</h1>
      <p className="muted">{quiz.kind === "practice" ? "Practice: free, unlimited, and it does not change your course result. " : quiz.kind === "final" ? "Final exam. " : "Topic test. "}Pass mark {quiz.pass_mark}%.{quiz.time_limit_minutes ? ` Time limit: ${quiz.time_limit_minutes} minutes, enforced by the server.` : ""}</p>
      <ol>{quiz.questions.map(q => (
        <li key={q.id}>
          <fieldset className="q"><legend>{q.prompt}{q.qtype === "multiple" ? " (choose all that apply)" : ""}</legend>
            {q.qtype === "short" ? (
              <input value={answers[q.id]?.[0] ?? ""} onChange={e => setAnswers(a => ({ ...a, [q.id]: [e.target.value] }))} maxLength={200} />
            ) : q.options.map(o => (
              <label key={o.id} className="opt">
                <input type={q.qtype === "single" ? "radio" : "checkbox"} name={`q${q.id}`} checked={(answers[q.id] ?? []).includes(o.id)}
                  onChange={e => pick(q, o.id, e.target.checked)} /> {o.text}
              </label>
            ))}
          </fieldset>
        </li>
      ))}</ol>
      {err && <p role="alert" className="err">{err}</p>}
      <button className="solid" onClick={submit}>Submit answers</button>
    </section>
  );
}
