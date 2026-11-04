import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, CourseDetail, LessonData, Progress } from "../api";

export default function LessonPage() {
  const { slug = "", lessonSlug = "" } = useParams();
  const nav = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [lesson, setLesson] = useState<LessonData | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null); setLesson(null); setNote(null);
    Promise.all([api.courseDetail(slug), api.lesson(slug, lessonSlug), api.courseProgress(slug)])
      .then(([c, l, p]) => { if (!cancelled) { setCourse(c); setLesson(l); setProgress(p); window.scrollTo(0, 0); } })
      .catch(e => { if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, "Could not load the lesson.")); });
    return () => { cancelled = true; };
  }, [slug, lessonSlug]);

  /** Marks the lesson done (once) and moves on: next lesson, or back to the course path after the last one. */
  async function next() {
    if (!lesson) return;
    setBusy(true); setNote(null);
    try {
      if (!lesson.completed) setProgress(await api.completeLesson(slug, lessonSlug));
      nav(lesson.next ? `/courses/${slug}/lessons/${lesson.next}` : `/courses/${slug}`);
    } catch (e) { setNote(e instanceof Error ? e.message : "Could not save progress."); }
    finally { setBusy(false); }
  }

  if (error) {
    return (
      <section className="page">
        <p role="alert" className="err">{error.message}</p>
        <Link to={`/courses/${slug}`}>{error.status === 403 ? "Go to the course page to enroll" : "Back to the course"}</Link>
      </section>
    );
  }
  if (!lesson || !course || !progress) return <section className="page"><p aria-live="polite">Loading…</p></section>;

  const all = course.outline?.flatMap(m => m.lessons) ?? [];
  const index = Math.max(0, all.findIndex(l => l.slug === lessonSlug));

  return (
    <div className="lesson-shell">
      <header className="lesson-top">
        <Link to={`/courses/${slug}`} className="close" aria-label="Back to the course">✕</Link>
        <div className="seg" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Course progress">
          {all.map(l => <span key={l.slug} className={progress.completed.includes(l.slug) ? "done" : l.slug === lessonSlug ? "now" : ""} />)}
        </div>
        <span className="count">{index + 1}/{all.length}</span>
      </header>
      <div className="lesson-layout">
        <aside aria-label="Course lessons" className="lesson-side">
          <h2><Link to={`/courses/${slug}`}>{course.title}</Link></h2>
          <p className="muted">{progress.percent}% complete</p>
          {course.outline?.map(m => (
            <div key={m.title}>
              <h3>{m.title}</h3>
              <ul className="side">
                {m.lessons.map(l => (
                  <li key={l.slug}>
                    <Link to={`/courses/${slug}/lessons/${l.slug}`} aria-current={l.slug === lessonSlug ? "page" : undefined}>
                      {progress.completed.includes(l.slug) ? "✓ " : ""}{l.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>
        <article className="lesson-card">
          <p className="chip">{lesson.module_title}</p>
          <h1>{lesson.title}</h1>
          <div className="md"><ReactMarkdown>{lesson.body_md}</ReactMarkdown></div>
          {lesson.example_code && (<>
            <h2>Example</h2>
            <pre className="example"><code>{lesson.example_code}</code></pre>
            {lesson.expected_output && (<><h3>Output</h3><pre className="example out"><code>{lesson.expected_output}</code></pre></>)}
            <p className="muted">Want to try it yourself? <Link to="/playground">Open the Playground</Link>.</p>
          </>)}
          {note && <p role="alert" className="err">{note}</p>}
        </article>
      </div>
      <footer className="lesson-bottom">
        {lesson.prev ? <Link className="ghost" to={`/courses/${slug}/lessons/${lesson.prev}`} aria-label="Previous lesson">←</Link> : <span />}
        <button className="solid big" onClick={next} disabled={busy}>
          {busy ? "Saving…" : lesson.next ? "Continue" : lesson.completed ? "Back to course" : "Finish course content"}
        </button>
      </footer>
    </div>
  );
}
