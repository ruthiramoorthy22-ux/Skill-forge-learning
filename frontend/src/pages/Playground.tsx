import { useState } from "react";
import { ApiError, http } from "../api";

const TEMPLATES: Record<string, string> = {
  python: 'name = input()\nprint("Hello, " + name)\n',
  java: 'import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner in = new Scanner(System.in);\n        System.out.println("Hello, " + in.nextLine());\n    }\n}\n',
  c: '#include <stdio.h>\n\nint main(void) {\n    char name[100];\n    scanf("%99s", name);\n    printf("Hello, %s\\n", name);\n    return 0;\n}\n',
  cpp: '#include <iostream>\n#include <string>\n\nint main() {\n    std::string name;\n    std::cin >> name;\n    std::cout << "Hello, " << name << "\\n";\n    return 0;\n}\n',
};
interface Result { stdout: string; stderr: string; compile_output: string; status: string; time: string | null }

export default function Playground() {
  const [lang, setLang] = useState("python");
  const [code, setCode] = useState(TEMPLATES.python);
  const [stdin, setStdin] = useState("Asha");
  const [out, setOut] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null); setOut(null);
    try { setOut(await http<Result>("/code/run", { method: "POST", body: { language: lang, source: code, stdin } })); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not run the code."); }
    finally { setBusy(false); }
  }

  return (
    <section className="page">
      <h1>Code playground</h1>
      <p className="muted">Code runs on a separate sandbox service, never on this site&apos;s server. If that service is not configured you will see a notice instead of a result.</p>
      <div className="filters">
        <label>Language
          <select value={lang} onChange={e => { setLang(e.target.value); setCode(TEMPLATES[e.target.value]); setOut(null); }}>
            <option value="python">Python</option><option value="java">Java</option><option value="c">C</option><option value="cpp">C++</option>
          </select>
        </label>
      </div>
      <label>Code
        <textarea className="editor" spellCheck={false} value={code} onChange={e => setCode(e.target.value)} rows={14} maxLength={20000} />
      </label>
      <label>Input (stdin)
        <textarea className="editor" spellCheck={false} value={stdin} onChange={e => setStdin(e.target.value)} rows={3} maxLength={5000} />
      </label>
      <div className="row">
        <button className="solid" onClick={run} disabled={busy}>{busy ? "Running…" : "Run code"}</button>
        <button className="ghost" onClick={() => setCode(TEMPLATES[lang])}>Reset code</button>
        <button className="ghost" onClick={() => { setOut(null); setError(null); }}>Clear output</button>
      </div>
      {error && <p role="alert" className="err">{error}</p>}
      {out && (
        <div aria-live="polite">
          <h2>Output <span className="tag">{out.status}</span></h2>
          {out.compile_output && <><h3>Compilation errors</h3><pre className="example"><code>{out.compile_output}</code></pre></>}
          {out.stderr && <><h3>Runtime errors</h3><pre className="example"><code>{out.stderr}</code></pre></>}
          <pre className="example out"><code>{out.stdout || "(no output)"}</code></pre>
        </div>
      )}
    </section>
  );
}
