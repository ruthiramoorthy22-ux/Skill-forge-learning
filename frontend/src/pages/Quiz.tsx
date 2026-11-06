import { useEffect, useRef, useState } from "react";
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
  const [questionIndex, setQuestionIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [res, setRes] = useState<Outcome | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [courseSlug, setCourseSlug] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const start = () => {
    setRes(null); setPending(null); setAnswers({}); setErr(null); setQuiz(null);
    setQuestionIndex(0); setSubmitting(false); submittingRef.current = false;
    http<Started>(`/quizzes/${id}/start`, { method: "POST" }).then(setQuiz).catch(e => setErr(e.message));
  };
  useEffect(start, [id]);

  async function submit() {
    if (!quiz || submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const out = await http<Outcome | Pending>(`/quizzes/${id}/submit`, { method: "POST", body: { attempt_id: quiz.attempt_id, answers } });
      if ("pending_review" in out) {  // final exam: no marks, no answers; the admin releases the result
        setPending(out.message);
        setCourseSlug(out.course_slug);
      } else setRes(out);
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not submit."); }
    finally { submittingRef.current = false; setSubmitting(false); }
  }
  const pick = (q: Q, opt: string, checked: boolean) => {
    setErr(null);
    setAnswers(a => {
      const cur = a[q.id] ?? [];
      return { ...a, [q.id]: q.qtype === "single" ? [opt] : checked ? [...cur, opt] : cur.filter(x => x !== opt) };
    });
  };

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
  const question = quiz.questions[questionIndex];
  if (!question) return <section className="page"><p role="alert" className="err">This quiz has no available questions.</p><Link to="/courses">Back to courses</Link></section>;
  const selected = answers[question.id] ?? [];
  const hasAnswer = question.qtype === "short" ? !!selected[0]?.trim() : selected.length > 0;
  const lastQuestion = questionIndex === quiz.questions.length - 1;
  return (
    <section className="page narrow exam-page">
      <header className="exam-header">
        <p className="muted exam-kind">{quiz.kind === "practice" ? "Practice" : quiz.kind === "final" ? "Final exam" : "Topic test"}</p>
        <h1>{quiz.title}</h1>
        <p className="muted">Pass mark {quiz.pass_mark}%.{quiz.time_limit_minutes ? ` Time limit: ${quiz.time_limit_minutes} minutes, enforced by the server.` : ""}</p>
      </header>
      <div className="exam-progress" aria-label={`Question ${questionIndex + 1} of ${quiz.questions.length}`}>
        <div className="exam-progress-label"><strong>Question {questionIndex + 1} of {quiz.questions.length}</strong><span>{Math.round(((questionIndex + 1) / quiz.questions.length) * 100)}%</span></div>
        <div className="bar-track" role="progressbar" aria-valuenow={questionIndex + 1} aria-valuemin={1} aria-valuemax={quiz.questions.length}>
          <div className="bar-fill" style={{ width: `${((questionIndex + 1) / quiz.questions.length) * 100}%` }} />
        </div>
      </div>
      <div className="q exam-question" key={question.id}>
        <h2>{question.prompt}</h2>
        {question.qtype === "multiple" && <p className="muted">Choose all that apply.</p>}
        <div className="exam-options">
          {question.qtype === "short" ? (
            <label className="exam-short-answer">Your answer
              <input value={selected[0] ?? ""} onChange={e => { setErr(null); setAnswers(a => ({ ...a, [question.id]: [e.target.value] })); }} maxLength={200} />
            </label>
          ) : question.options.map((o, i) => (
            <label key={o.id} className={`opt exam-option${selected.includes(o.id) ? " selected" : ""}`}>
              <input type={question.qtype === "single" ? "radio" : "checkbox"} name={`q${question.id}`} checked={selected.includes(o.id)}
                onChange={e => pick(question, o.id, e.target.checked)} />
              <span className="exam-option-letter">{String.fromCharCode(65 + i)}</span><span>{o.text}</span>
            </label>
          ))}
        </div>
      </div>
      {err && <p role="alert" className="err">{err}</p>}
      {!hasAnswer && <p className="muted exam-hint">Choose an answer to continue.</p>}
      <nav className="exam-navigation" aria-label="Question navigation">
        <button className="ghost" disabled={questionIndex === 0 || submitting} onClick={() => { setErr(null); setQuestionIndex(i => i - 1); }}>Previous</button>
        {lastQuestion ? (
          <button className="solid" disabled={!hasAnswer || submitting} onClick={submit}>{submitting ? "Submitting…" : quiz.kind === "final" ? "Submit Exam" : quiz.kind === "practice" ? "Submit practice" : "Submit Test"}</button>
        ) : (
          <button className="solid" disabled={!hasAnswer || submitting} onClick={() => { setErr(null); setQuestionIndex(i => i + 1); }}>Next</button>
        )}
      </nav>
    </section>
  );
}
