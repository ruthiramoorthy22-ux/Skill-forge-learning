import { ChangeEvent, FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { errText, http } from "../api";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;
const FIELDS: [string, string][] = [["name", "Student name"], ["course", "Course name"], ["date", "Date"], ["cert_id", "Certificate ID"]];

/** Certificate designs: upload a design image, click where the name / course / date go, preview with sample data, activate. */
export function CertificateDesigner() {
  const [data, setData] = useState<Obj | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [edit, setEdit] = useState<{ id: number; title: string; fields: Obj } | null>(null);
  const [active, setActive] = useState("name");
  const [preview, setPreview] = useState("");
  const [sample, setSample] = useState({ name: "Ruthiramoorthy", course: "Introduction to Python" });
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(() => { http<Obj>("/admin/certificate-templates").then(setData).catch(e => setErr(errText(e))); }, []);
  useEffect(load, [load]);

  // The preview is drawn by the server with the same code that draws real certificates, so what you see is what students get.
  useEffect(() => {
    if (!edit) return;
    const t = setTimeout(() => {
      http<{ image: string }>("/admin/certificate-templates/preview", { method: "POST", body: { template_id: edit.id, fields: edit.fields, name: sample.name, course: sample.course } })
        .then(r => setPreview(r.image)).catch(e => setErr(errText(e)));
    }, 300);
    return () => clearTimeout(t);
  }, [edit, sample]);

  async function upload(e: FormEvent) {
    e.preventDefault(); setErr(null); setMsg(null);
    const f = file.current?.files?.[0];
    if (!f) { setErr("Choose the certificate design image first."); return; }
    if (!/^image\/(png|jpeg)$/.test(f.type)) { setErr("Upload a PNG or JPG image."); return; }
    if (f.size > 8_000_000) { setErr("The image is larger than 8 MB."); return; }
    setBusy(true);
    try {
      const image = await new Promise<string>((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = () => rej(new Error("Could not read the file.")); r.readAsDataURL(f); });
      const t = await http<Obj>("/admin/certificate-templates", { method: "POST", body: { name: name.trim() || f.name, image } });
      setName(""); if (file.current) file.current.value = "";
      setMsg("Design uploaded. Click on the preview to place the student name, course and date, then Save.");
      setEdit({ id: t.id, title: t.name, fields: t.fields }); load();
    } catch (er) { setErr(errText(er)); } finally { setBusy(false); }
  }

  const setField = (patch: Obj) => edit && setEdit({ ...edit, fields: { ...edit.fields, [active]: { ...edit.fields[active], ...patch } } });
  function place(e: React.MouseEvent<HTMLImageElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    setField({ x: Math.round(((e.clientX - r.left) / r.width) * 1000) / 1000, y: Math.round(((e.clientY - r.top) / r.height) * 1000) / 1000 });
  }
  async function save() {
    if (!edit) return; setErr(null); setMsg(null);
    try { await http(`/admin/certificate-templates/${edit.id}`, { method: "PATCH", body: { fields: edit.fields } }); setMsg("Placement saved."); load(); } catch (e) { setErr(errText(e)); }
  }
  async function openEdit(t: Obj) { setMsg(null); setErr(null); setPreview(""); setEdit({ id: t.id, title: t.name, fields: t.fields }); }
  async function activate(t: Obj) {
    try { await http(`/admin/certificate-templates/${t.id}/activate`, { method: "POST" }); setMsg(`"${t.name}" is now used for every certificate.`); load(); } catch (e) { setErr(errText(e)); }
  }
  async function builtin() {
    try { await http("/admin/certificate-templates/use-builtin", { method: "POST" }); setMsg("The built-in Skill Forge Learning design is used again."); load(); } catch (e) { setErr(errText(e)); }
  }
  async function remove(t: Obj) {
    if (!window.confirm(`Delete the design "${t.name}"?`)) return;
    try { await http(`/admin/certificate-templates/${t.id}`, { method: "DELETE" }); if (edit?.id === t.id) setEdit(null); load(); } catch (e) { setErr(errText(e)); }
  }
  const cur = edit?.fields[active];

  return (
    <>
      <h3>Certificate design</h3>
      <p className="muted">Every certificate is drawn on the active design with the student's name, the course and the date taken from the database. Upload your own design image (PNG or JPG, at least 600 x 400, up to 8 MB). Leave the places for the name, course and date empty in your image. Certificates already issued use the active design when they are downloaded or emailed.</p>
      {err && <p role="alert" className="err">{err}</p>}
      {msg && <p role="status">{msg}</p>}
      {data && (
        <div className="scroll"><table><thead><tr><th>Design</th><th>Size</th><th>Status</th><th></th></tr></thead><tbody>
          <tr><td>Built-in Skill Forge Learning design</td><td>1344 x 896</td><td>{data.builtin.active ? "✅ In use" : "-"}</td>
            <td>{!data.builtin.active && <button className="ghost" onClick={builtin}>Use this design</button>}</td></tr>
          {data.items.map((t: Obj) => (
            <tr key={t.id}><td>{t.name}</td><td>{t.width} x {t.height}</td><td>{t.active ? "✅ In use" : "-"}</td>
              <td><button className="ghost" onClick={() => openEdit(t)}>Place text</button>{" "}
                {!t.active && <button className="solid" onClick={() => activate(t)}>Use this design</button>}{" "}
                {!t.active && <button className="ghost" onClick={() => remove(t)}>Delete</button>}</td></tr>))}
        </tbody></table></div>
      )}
      <form className="form" onSubmit={upload} style={{ maxWidth: 520, marginTop: 16 }}>
        <h4>Upload a new design</h4>
        <label>Design name<input value={name} onChange={e => setName(e.target.value)} maxLength={120} placeholder="Diwali 2026 certificate" /></label>
        <label>Design image<input ref={file} type="file" accept="image/png,image/jpeg" onChange={(_e: ChangeEvent<HTMLInputElement>) => setMsg(null)} /></label>
        <button className="solid" disabled={busy}>{busy ? "Uploading…" : "Upload design"}</button>
      </form>

      {edit && (
        <div className="designer">
          <h4>Place the text: {edit.title}</h4>
          <div className="row" role="radiogroup" aria-label="Which text to place">
            {FIELDS.map(([k, label]) => <button key={k} type="button" role="radio" aria-checked={active === k} className={active === k ? "solid" : "ghost"} onClick={() => setActive(k)}>{label}</button>)}
          </div>
          <p className="muted">1. Choose a text above. 2. Click on the certificate where its baseline centre should be. 3. Adjust the size and colour. 4. Save.</p>
          {preview ? <img className="designer-img" src={preview} alt="Certificate preview. Click to place the selected text." onClick={place} /> : <p aria-live="polite">Drawing the preview…</p>}
          {cur && (
            <div className="form" style={{ maxWidth: 520 }}>
              <label className="opt"><input type="checkbox" checked={cur.visible} onChange={e => setField({ visible: e.target.checked })} /> Show this text</label>
              <label>Size ({Math.round(cur.size * 1000) / 10}% of the height)<input type="range" min={0.01} max={0.15} step={0.001} value={cur.size} onChange={e => setField({ size: Number(e.target.value) })} /></label>
              <label>Longest width allowed ({Math.round(cur.max_width * 100)}% of the width)<input type="range" min={0.1} max={1} step={0.01} value={cur.max_width} onChange={e => setField({ max_width: Number(e.target.value) })} /></label>
              <label>Colour<input type="color" value={cur.color} onChange={e => setField({ color: e.target.value })} /></label>
              <label>Font<select value={cur.font} onChange={e => setField({ font: e.target.value })}>{data?.fonts.map((f: string) => <option key={f}>{f}</option>)}</select></label>
              <label>Text before it (for example "Date: ")<input maxLength={30} value={cur.prefix} onChange={e => setField({ prefix: e.target.value })} /></label>
            </div>
          )}
          <div className="form" style={{ maxWidth: 520 }}>
            <label>Sample student name<input maxLength={60} value={sample.name} onChange={e => setSample({ ...sample, name: e.target.value })} /></label>
            <label>Sample course name<input maxLength={90} value={sample.course} onChange={e => setSample({ ...sample, course: e.target.value })} /></label>
          </div>
          <div className="row"><button className="solid" onClick={save}>Save placement</button><button className="ghost" onClick={() => setEdit(null)}>Close</button></div>
        </div>
      )}
    </>
  );
}
