import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ProjectSubmit from "../components/ProjectSubmit";
import { API_BASE, api, ApiError, CourseDetail, errText, http, openCertificate, Progress } from "../api";
import { useAuth } from "../auth";
import { loadRazorpay } from "../razorpay";

interface QuizMeta { id: number; title: string; kind: "chapter" | "final" | "practice"; pass_mark: number; time_limit_minutes: number | null; question_count: number }
interface Exam { unlocked: boolean; message: string; missing_lessons: string[]; missing_tests: string[]; rule: string }
interface Cert { price_inr: number; is_free?: boolean; can_pay?: boolean; payments_configured: boolean; course_completed: boolean; paid: boolean; awaiting_admin?: boolean; issued: boolean; certificate_id: string | null; locked_reason: string | null; final_result?: { state: "none" | "pending" | "released"; passed?: boolean } }
interface Order { order_id: string; amount: number; currency: string; key_id: string; course_title: string; student_name: string; student_email: string }

export default function CourseDetailPage() {
  const { slug = "" } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [quizzes, setQuizzes] = useState<QuizMeta[]>([]);
  const [exam, setExam] = useState<Exam | null>(null);
  const [cert, setCert] = useState<Cert | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [price, setPrice] = useState<number | null>(null);

  useEffect(() => {
    http<{ certificate_price_inr: number }>("/pricing").then(r => setPrice(r.certificate_price_inr)).catch(() => undefined);
  }, []);

  useEffect(() => {
    setCourse(null); setError(null);
    api.courseDetail(slug).then(setCourse).catch(e => setError(e.message));
    http<{ items: QuizMeta[] }>(`/courses/${slug}/quizzes`).then(r => setQuizzes(r.items)).catch(() => undefined);
  }, [slug]);

  const refresh = useCallback(() => {
    if (!user) return;
    api.courseProgress(slug).then(p => {
      setProgress(p);
      if (!p.enrolled) return;
      http<Exam>(`/courses/${slug}/exam-status`).then(setExam).catch(() => undefined);
      http<Cert>(`/courses/${slug}/certificate`).then(setCert).catch(() => undefined);
    }).catch(() => undefined);
  }, [user, slug]);
  useEffect(() => { setProgress(null); setExam(null); setCert(null); if (course?.outline) refresh(); }, [course, refresh]);

  if (error) return <section className="page"><p role="alert" className="err">{error}</p><Link to="/courses">Back to the catalog</Link></section>;
  if (!course) return <section className="page"><p aria-live="polite">Loading…</p></section>;
  const first = course.outline?.[0]?.lessons[0]?.slug;
  const enrolled = !!progress?.enrolled;

  async function start() {
    setBusy(true); setError(null);
    try {
      const p = progress?.enrolled ? progress : await api.enroll(slug);
      setProgress(p);
      const target = p.last_lesson ?? first;
      if (target) nav(`/courses/${slug}/lessons/${target}`);
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not start the course."); }
    finally { setBusy(false); }
  }

  const byKind = (k: QuizMeta["kind"]) => quizzes.filter(q => q.kind === k);
  const meta = (q: QuizMeta) => `${q.question_count} questions · pass ${q.pass_mark}%${q.time_limit_minutes ? ` · ${q.time_limit_minutes} min` : ""}`;
  const quizCard = (q: QuizMeta, icon: string) => enrolled
    ? <Link key={q.id} className="tile" to={`/quizzes/${q.id}`}><span className="tile-ico">{icon}</span><span><strong>{q.title}</strong><small>{meta(q)}</small></span><span className="go">›</span></Link>
    : <div key={q.id} className="tile off"><span className="tile-ico">🔒</span><span><strong>{q.title}</strong><small>Enroll to unlock</small></span></div>;

  const allLessons = course.outline?.flatMap(m => m.lessons) ?? [];
  const nextSlug = progress?.last_lesson ?? allLessons.find(l => !progress?.completed.includes(l.slug))?.slug ?? first;
  const lessonsDone = !!progress && progress.total > 0 && progress.completed.length >= progress.total;
  const testsDone = !!exam && exam.missing_tests.length === 0;
  const finalOpen = !!exam?.unlocked;
  const steps = [
    ["Lessons", lessonsDone], ["Tests", lessonsDone && testsDone], ["Final exam", !!cert?.course_completed],
    ...(cert?.is_free ? [] : [["Pay", !!cert?.paid]]), ["Certificate", !!cert?.issued],
  ] as [string, boolean][];
  const shownPrice = cert?.price_inr ?? price;
  const previewUrl = `${API_BASE}/api/courses/${slug}/certificate/preview`;

  return (
    <section className="page course-page">
      <div className="course-hero">
        <p className="chips"><span className={`tag ${course.level}`}>{course.level}</span> <span className="tag">{course.category_name}</span></p>
        <h1>{course.title}</h1>
        {course.price_inr !== undefined && <p><span className={`tag price ${course.is_free ? "free" : "paid"}`}>{course.is_free ? "Free course · free certificate" : `Certificate ₹${course.price_inr}`}</span></p>}
        {(course.outline || (course.duration_value && course.duration_unit)) && <p className="muted">
          {course.outline && `${course.lesson_count} lessons · `}
          {course.duration_value && course.duration_unit
            ? `Duration: ${course.duration_value} ${course.duration_unit[0].toUpperCase()}${course.duration_unit.slice(1)}`
            : `about ${course.est_minutes} minutes`}
        </p>}
        {enrolled && progress && (<>
          <div className="bar-track fat" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}><div className="bar-fill" style={{ width: `${progress.percent}%` }} /></div>
          <p className="muted">{progress.completed.length} of {progress.total} lessons ({progress.percent}%)</p>
        </>)}
      </div>
      {!course.outline ? (
        <p>Lessons for this course are not published yet. See the <Link to="/courses">catalog</Link> for courses that are ready.</p>
      ) : (
        <>
          <p className="lead">{course.summary}</p>
          {user ? (
            <button className="solid big wide" onClick={start} disabled={busy}>
              {busy ? "Please wait…" : enrolled ? (progress!.completed.length ? "Continue learning" : "Start learning") : "Enroll and start"}
            </button>
          ) : <p><Link to="/signin">Sign in</Link> or <Link to="/register">create an account</Link> to enroll and track your progress.</p>}
          {error && <p role="alert" className="err">{error}</p>}

          {course.objectives && course.objectives.length > 0 && (<><h2>What you will learn</h2>
            <ul className="plain">{course.objectives.map(o => <li key={o}>{o}</li>)}</ul></>)}

          <h2>Course path</h2>
          <div className="path">
            {course.outline.map(m => (
              <div key={m.title} className="path-module">
                <h3>{m.title}</h3>
                <ol>
                  {m.lessons.map((l, i) => {
                    const done = !!progress?.completed.includes(l.slug);
                    const state = done ? "done" : enrolled && l.slug === nextSlug ? "next" : "";
                    const inner = (<><span className={`node ${state}`} aria-hidden="true">{done ? "✓" : state === "next" ? "▶" : i + 1}</span><span className="lname">{l.title}{done ? <span className="sr"> (done)</span> : null}</span></>);
                    return <li key={l.slug}>{enrolled ? <Link to={`/courses/${slug}/lessons/${l.slug}`}>{inner}</Link> : <span className="locked">{inner}</span>}</li>;
                  })}
                </ol>
              </div>
            ))}
          </div>

          {byKind("chapter").length > 0 && (<><h2>Lesson tests</h2><div className="tiles">{byKind("chapter").map(q => quizCard(q, "📝"))}</div></>)}
          {byKind("practice").length > 0 && (<><h2>Practice</h2><p className="muted">Free and optional. Practice never changes your result.</p>
            <div className="tiles">{byKind("practice").map(q => quizCard(q, "🎯"))}</div></>)}
          {byKind("final").length > 0 && (<><h2>Final exam</h2>
            {byKind("final").map(q => !enrolled ? <div key={q.id} className="tile off"><span className="tile-ico">🔒</span><span><strong>{q.title}</strong><small>Enroll to work towards the final exam</small></span></div>
              : !exam ? <p key={q.id}>Checking…</p>
              : !exam.unlocked ? <div key={q.id} className="tile off"><span className="tile-ico">🔒</span><span><strong>{q.title} is locked</strong><small>{exam.message}</small></span></div>
              : cert?.final_result && cert.final_result.state !== "none" && !(cert.final_result.state === "released" && cert.final_result.passed === false)
                ? <Link key={q.id} className="tile" to={`/courses/${slug}/result`}><span className="tile-ico">{cert.final_result.state === "pending" ? "⏳" : "✅"}</span><span><strong>{q.title}</strong><small>{cert.final_result.state === "pending" ? "Submitted. Waiting for the admin to release your result" : "Result released. Tap to see it"}</small></span><span className="go">›</span></Link>
              : quizCard(q, "🏁"))}</>)}

          {enrolled && (<><h2>Optional project</h2>
            <p className="muted">Build and submit a project for practice. Projects are optional and do not affect course completion or certificate eligibility.</p>
            <ProjectSubmit slug={slug} onChange={refresh} /></>)}

          <h2>Certificate</h2>
          <div className="cert-card">
            <div className={`cert-preview ${cert?.issued ? "" : "locked"}`}>
              <img src={previewUrl} alt="Sample certificate for this course" loading="lazy" />
              {!cert?.issued && <div className="lock-badge" aria-hidden="true">🔒 Locked</div>}
            </div>
            <ol className="steps" aria-label="Steps to the certificate">
              {steps.map(([label, ok]) => <li key={label} className={ok ? "ok" : ""}><span>{ok ? "✓" : "•"}</span>{label}</li>)}
            </ol>
            {!enrolled || !cert ? <p>This is a sample. Complete every lesson and pass the final exam{cert?.is_free || course.is_free ? "" : <>, then pay{shownPrice !== null ? ` ₹${shownPrice}` : ""}</>} to unlock your own certificate. Projects are optional.</p>
              : cert.issued ? (<>
                <p><strong>🏅 Your certificate is ready.</strong></p>
                <div className="row">
                  <button className="solid" onClick={() => openCertificate(cert.certificate_id!, "pdf").catch(e => setNote(errText(e)))}>Download PDF</button>
                  <button className="ghost" onClick={() => openCertificate(cert.certificate_id!, "png").catch(e => setNote(errText(e)))}>Download image</button>
                </div></>)
              : !cert.course_completed ? <p>{finalOpen ? "Take the final exam. The admin releases your result, then you can continue to payment." : cert.locked_reason}</p>
              : cert.awaiting_admin ? <p><strong>✅ {cert.is_free ? "Course completed." : "Payment received."}</strong> The admin will unlock your certificate shortly. You will find it here and in your dashboard.</p>
              : cert.is_free ? (<><p>This course is free. Open the next screen to get your certificate.</p>
                  <Link className="solid big wide" to={`/courses/${slug}/pay`}>Get my certificate</Link></>)
              : !cert.can_pay ? <p>You finished the course. Online payment is not available right now, so the certificate cannot be bought at the moment.</p>
              : (<><p>Your course is complete. Pay ₹{cert.price_inr} to unlock your certificate.</p>
                  <Link className="solid big wide" to={`/courses/${slug}/pay`}>Pay now ₹{cert.price_inr}</Link></>)}
            {note && <p role="status">{note}</p>}
          </div>
        </>
      )}
    </section>
  );
}
