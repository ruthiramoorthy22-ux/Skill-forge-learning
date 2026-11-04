import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errText, http } from "../api";

interface N { id: number; kind: string; title: string; message: string; link: string; read: boolean; at: string }
const ICON: Record<string, string> = { new_course: "📚", new_challenge: "💻", project: "📝", payment: "💳", certificate: "🏅", result: "🎯", announcement: "📣" };

/** The student's notifications: new courses and challenges, project review, payments, certificates, announcements. */
export default function Notifications() {
  const nav = useNavigate();
  const [items, setItems] = useState<N[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { http<{ items: N[] }>("/me/notifications").then(r => setItems(r.items)).catch(e => setErr(errText(e))); }, []);
  useEffect(load, [load]);
  const changed = () => window.dispatchEvent(new Event("sf-notifications"));

  async function open(n: N) {
    if (!n.read) { await http(`/me/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined); changed(); }
    if (n.link) nav(n.link); else load();
  }
  async function readAll() { await http("/me/notifications/read-all", { method: "POST" }).catch(() => undefined); changed(); load(); }

  return (
    <section className="page narrow">
      <h1>Notifications</h1>
      {err && <p role="alert" className="err">{err}</p>}
      {items && items.some(n => !n.read) && <p><button className="ghost" onClick={readAll}>Mark all as read</button></p>}
      {items && items.length === 0 && <p>Nothing yet. New courses, new challenges and updates from the admin will appear here.</p>}
      <ul className="notif-list">
        {items?.map(n => (
          <li key={n.id} className={n.read ? "" : "unread"}>
            <button onClick={() => open(n)}>
              <span className="n-ico" aria-hidden="true">{ICON[n.kind] ?? "🔔"}</span>
              <span><strong>{n.title}</strong>{n.message && <small>{n.message}</small>}<small className="when">{new Date(n.at).toLocaleString()}</small></span>
            </button>
          </li>
        ))}
      </ul>
      <p><Link to="/home">Back to home</Link></p>
    </section>
  );
}
