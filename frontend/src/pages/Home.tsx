import { Link } from "react-router-dom";

export default function Home() {
  return (
    <>
      <section className="hero">
        <div>
          <h1>Learn programming one working program at a time.</h1>
          <p className="lead">
            Skill Learning is a coding platform for beginners through interview candidates, covering languages,
            web, data, AI, cloud and security. It is being built in phases, and this site shows exactly what exists today.
          </p>
          <div className="row">
            <Link className="solid" to="/courses">Browse the catalog</Link>
            <Link className="ghost" to="/paths">See learning paths</Link>
          </div>
        </div>
        <figure className="panel" aria-label="Example of the planned lesson layout">
          <figcaption>Planned lesson layout (the interactive editor arrives in a later phase)</figcaption>
          <pre><code>{`# Lesson: Lists in Python
names = ["Asha", "Ravi", "Mei"]
for name in names:
    print(name.upper())`}</code></pre>
          <pre className="out"><code>{`Expected output
ASHA
RAVI
MEI`}</code></pre>
        </figure>
      </section>
      <section className="page">
        <h2>Where the build stands</h2>
        <ul className="plain">
          <li><strong>Ready:</strong> public pages, course catalog with search and filters, light and dark themes.</li>
          <li><strong>Next:</strong> accounts and the database, then lessons, quizzes, the code editor and the admin dashboard.</li>
          <li><strong>Not connected yet:</strong> code execution (needs Judge0).</li>
        </ul>
      </section>
    </>
  );
}
