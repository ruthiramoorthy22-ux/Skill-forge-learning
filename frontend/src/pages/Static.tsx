import { ReactNode, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { api, Category } from "../api";

const Page = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="page"><h1>{title}</h1>{children}</section>
);

export const About = () => (
  <Page title="About Skill Learning">
    <p>Skill Learning is an original programming education platform with its own lessons, exercises and branding.
      It is under active construction and is delivered in phases, so features appear here only once they work.</p>
  </Page>
);

export function Paths() {
  const [cats, setCats] = useState<Category[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api.categories().then(r => setCats(r.items)).catch(() => setErr(true)); }, []);
  return (
    <Page title="Learning paths">
      <p className="muted">Each path groups courses from beginner to advanced. All paths are planned; lessons are not published yet.</p>
      {err && <p role="alert" className="err">Could not load paths. Check that the backend is running.</p>}
      {!cats && !err && <p>Loading paths…</p>}
      <ul className="grid">
        {cats?.map(c => (
          <li key={c.id} className="card">
            <h3>{c.name}</h3>
            <p className="muted">{c.course_count} planned courses</p>
            <Link to={`/courses`}>Browse courses</Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function Projects() {
  const [items, setItems] = useState<{ slug: string; title: string; level: string; summary: string; body_md: string; status: string }[] | null>(null);
  const [err, setErr] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { api.projects().then(r => setItems(r.items)).catch(() => setErr(true)); }, []);
  return (
    <Page title="Projects">
      <p className="muted">Build real things step by step. Projects marked Planned are coming soon.</p>
      {err && <p role="alert" className="err">Could not load projects. Check that the backend is running.</p>}
      {!items && !err && <p>Loading projects…</p>}
      <ul className="grid">{items?.map(p => (
        <li key={p.slug} className="card">
          <h3>{p.title}</h3>
          <p className="muted">{p.summary}</p>
          <p><span className={`tag ${p.level}`}>{p.level}</span> {p.status === "planned" && <span className="tag">Planned</span>}</p>
          {p.status === "available" && <button className="ghost" onClick={() => setOpen(open === p.slug ? null : p.slug)}>{open === p.slug ? "Hide steps" : "Open project"}</button>}
          {open === p.slug && <div className="md"><ReactMarkdown>{p.body_md}</ReactMarkdown></div>}
        </li>))}</ul>
    </Page>
  );
}

export const Help = () => (
  <Page title="Help and contact">
    <p>A support contact has not been published yet. It will appear here before accounts open.</p>
  </Page>
);

export const Privacy = () => (
  <Page title="Privacy Policy">
    <p className="notice">Draft placeholder. This site collects no personal data today because accounts are not connected. A full policy must be written and legally reviewed before launch.</p>
  </Page>
);

export const Terms = () => (
  <Page title="Terms of Service">
    <p className="notice">Draft placeholder. Terms must be written and legally reviewed before launch.</p>
  </Page>
);
