import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { errText, http } from "../api";
import { useAuth } from "../auth";
import Avatar, { setAvatarCache } from "../components/Avatar";

interface P { display_name: string; email: string; phone: string; college_name: string; school_name: string; tenth_mark: string; twelfth_mark: string; degree: string; year_of_study: string; city: string; avatar?: string }
const EMPTY: P = { display_name: "", email: "", phone: "", college_name: "", school_name: "", tenth_mark: "", twelfth_mark: "", degree: "", year_of_study: "", city: "" };

/** Student profile: personal and education details, saved on the server. */
export default function Profile() {
  const { user, setUser } = useAuth();
  const [f, setF] = useState<P>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { http<P>("/me/profile").then(p => { setF(p); setLoaded(true); }).catch(e => setMsg({ ok: false, text: errText(e) })); }, []);
  const set = (k: keyof P) => (e: { target: { value: string } }) => { setF({ ...f, [k]: e.target.value }); setMsg(null); };

  const fileRef = useRef<HTMLInputElement>(null);
  const [picBusy, setPicBusy] = useState(false);

  /** Shrinks the chosen picture to 256 x 256 in the browser first, so the upload is small and fast. */
  async function pickPicture(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) { setMsg({ ok: false, text: "Choose a PNG, JPG or WebP picture." }); return; }
    setPicBusy(true); setMsg(null);
    try {
      const bmp = await createImageBitmap(file);
      const side = Math.min(bmp.width, bmp.height), canvas = document.createElement("canvas");
      canvas.width = canvas.height = 256;
      canvas.getContext("2d")!.drawImage(bmp, (bmp.width - side) / 2, (bmp.height - side) / 2, side, side, 0, 0, 256, 256);
      const out = await http<{ avatar: string }>("/me/avatar", { method: "PUT", body: { image: canvas.toDataURL("image/jpeg", 0.9) } });
      setF(x => ({ ...x, avatar: out.avatar })); setAvatarCache(out.avatar);
      setMsg({ ok: true, text: "Profile picture updated." });
    } catch (er) { setMsg({ ok: false, text: errText(er, "Could not use that picture.") }); }
    finally { setPicBusy(false); }
  }
  async function removePicture() {
    setPicBusy(true);
    try { await http("/me/avatar", { method: "DELETE" }); setF(x => ({ ...x, avatar: "" })); setAvatarCache(""); }
    catch (er) { setMsg({ ok: false, text: errText(er) }); } finally { setPicBusy(false); }
  }

  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      const { email: _email, avatar: _avatar, ...body } = f; // email is read-only; the picture has its own buttons
      const out = await http<P>("/me/profile", { method: "PUT", body });
      setF(out);
      if (user) setUser({ ...user, display_name: out.display_name });
      setMsg({ ok: true, text: "Profile saved." });
    } catch (er) { setMsg({ ok: false, text: errText(er, "Could not save.") }); }
    finally { setBusy(false); }
  }
  if (!user) return null;
  const filled = [f.phone, f.college_name, f.school_name, f.tenth_mark, f.twelfth_mark, f.degree, f.year_of_study, f.city].filter(Boolean).length;

  return (
    <section className="page narrow">
      <div className="profile-head">
        <Avatar name={f.display_name || user.display_name} src={f.avatar} className="xl" />
        <div><h1>My profile</h1><p className="muted">{user.email} · joined {new Date(user.created_at).toLocaleDateString()}</p>
          <div className="row" style={{ marginTop: 6 }}>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={pickPicture} />
            <button type="button" className="ghost" disabled={picBusy} onClick={() => fileRef.current?.click()}>{f.avatar ? "Change picture" : "Add profile picture"}</button>
            {f.avatar && <button type="button" className="ghost" disabled={picBusy} onClick={removePicture}>Remove</button>}
          </div></div>
      </div>
      <div className="bar-track" role="progressbar" aria-valuenow={Math.round(filled / 8 * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Profile completion">
        <div className="bar-fill" style={{ width: `${Math.round(filled / 8 * 100)}%` }} />
      </div>
      <p className="muted">{filled === 8 ? "Your profile is complete." : `${8 - filled} detail${8 - filled === 1 ? "" : "s"} left. Your details are visible to the admin of this platform only.`}</p>
      <form className="card form-grid" onSubmit={save}>
        <h2>Personal details</h2>
        <label>Full name (shown on your certificate)<input required maxLength={80} value={f.display_name} onChange={set("display_name")} /></label>
        <label>Email<input value={f.email} disabled readOnly /></label>
        <label>Phone number<input type="tel" inputMode="tel" maxLength={20} placeholder="+91 98765 43210" value={f.phone} onChange={set("phone")} autoComplete="tel" /></label>
        <label>City<input maxLength={80} value={f.city} onChange={set("city")} /></label>
        <h2>School</h2>
        <label>School name<input maxLength={160} value={f.school_name} onChange={set("school_name")} /></label>
        <label>10th mark (percentage or marks/total)<input inputMode="decimal" maxLength={12} placeholder="e.g. 88.4 or 442/500" value={f.tenth_mark} onChange={set("tenth_mark")} /></label>
        <label>12th mark (percentage or marks/total)<input inputMode="decimal" maxLength={12} placeholder="e.g. 91 or 546/600" value={f.twelfth_mark} onChange={set("twelfth_mark")} /></label>
        <h2>College</h2>
        <label>College name<input maxLength={160} value={f.college_name} onChange={set("college_name")} /></label>
        <label>Degree and department<input maxLength={120} placeholder="B.E. Computer Science" value={f.degree} onChange={set("degree")} /></label>
        <label>Year of study<input maxLength={30} placeholder="3rd year" value={f.year_of_study} onChange={set("year_of_study")} /></label>
        <div className="row"><button className="solid" disabled={busy || !loaded}>{busy ? "Saving…" : "Save profile"}</button><Link className="ghost" to="/home">Back to home</Link></div>
        {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "ok" : "err"}>{msg.text}</p>}
        <p className="muted">If a certificate was issued, your name is locked. Ask the admin to change it.</p>
      </form>
    </section>
  );
}
