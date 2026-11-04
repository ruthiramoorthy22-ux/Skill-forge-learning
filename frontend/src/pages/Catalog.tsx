import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Category, Course, statusLabel } from "../api";

const PAGE_SIZE = 24;

export default function Catalog() {
  const [cats, setCats] = useState<Category[]>([]);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [level, setLevel] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ items: Course[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.categories().then(r => setCats(r.items)).catch(() => undefined); }, []);

  useEffect(() => {
    const p = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (q.trim()) p.set("q", q.trim());
    if (category) p.set("category", category);
    if (level) p.set("level", level);
    let cancelled = false;
    setError(null);
    const t = setTimeout(() => {
      api.courses(p.toString())
        .then(r => { if (!cancelled) setData(r); })
        .catch(e => { if (!cancelled) { setData(null); setError(e.message); } });
    }, 200);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, category, level, page]);

  const reset = (fn: (v: string) => void) => (v: string) => { fn(v); setPage(1); };
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <section className="page">
      <h1>Course catalog</h1>
      <p className="muted">Levels are provisional and only courses marked Available have lessons, and those are short starter courses. Other labels show what is planned.</p>
      <div className="filters" role="search">
        <label>Search<input value={q} onChange={e => reset(setQ)(e.target.value)} placeholder="Course title" /></label>
        <label>Category
          <select value={category} onChange={e => reset(setCategory)(e.target.value)}>
            <option value="">All categories</option>
            {cats.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>Level
          <select value={level} onChange={e => reset(setLevel)(e.target.value)}>
            <option value="">All levels</option>
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
        </label>
      </div>
      {error && <p role="alert" className="err">Could not load courses ({error}). Check that the backend is running on port 8000.</p>}
      {!error && !data && <p aria-live="polite">Loading courses…</p>}
      {data && data.items.length === 0 && <p>No courses match these filters. Clear the search or choose another category.</p>}
      {data && data.items.length > 0 && (
        <>
          <p aria-live="polite">{data.total} courses</p>
          <ul className="grid">
            {data.items.map(c => (
              <li key={c.slug} className="card">
                <h3>{c.status === "available" ? <Link to={`/courses/${c.slug}`}>{c.title}</Link> : c.title}</h3>
                <p className="muted">{c.category_name}</p>
                <p><span className={`tag ${c.level}`}>{c.level}</span> <span className="tag">{statusLabel[c.status]}{c.status === "available" && c.lesson_count ? ` · ${c.lesson_count} lessons` : ""}</span>
                  {c.status === "available" && c.price_inr !== undefined && <span className={`tag price ${c.is_free ? "free" : "paid"}`}>{c.is_free ? "Free" : `Certificate ₹${c.price_inr}`}</span>}</p>
              </li>
            ))}
          </ul>
          <div className="row pager">
            <button className="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
            <span>Page {page} of {pages}</span>
            <button className="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>
        </>
      )}
    </section>
  );
}
