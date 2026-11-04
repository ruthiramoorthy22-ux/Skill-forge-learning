import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { errText, http } from "../api";

export interface Pay {
  id: string; course: string; course_slug: string; amount_inr: number; status: string; gateway: string; method: string;
  reference: string | null; failure_reason: string; created_at: string | null; paid_at: string | null; certificate_issued?: boolean;
}
const LABEL: Record<string, string> = { verified: "Paid", failed: "Failed", in_review: "Waiting for admin", pending: "Not completed", refunded: "Refunded" };
const how = (p: Pay) => (p.gateway === "upi_manual" ? "UPI (direct)" : p.method ? `Razorpay · ${p.method}` : "Razorpay");
const when = (p: Pay) => { const d = p.paid_at ?? p.created_at; return d ? new Date(d).toLocaleString() : ""; };

/** Payment history table. Used on the dashboard and on /payments. */
export function PaymentHistory({ compact = false }: { compact?: boolean }) {
  const [items, setItems] = useState<Pay[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { http<{ items: Pay[] }>("/me/payments").then(r => setItems(r.items)).catch(e => setErr(errText(e))); }, []);
  if (err) return <p role="alert" className="err">{err}</p>;
  if (!items) return <p aria-live="polite">Loading…</p>;
  if (items.length === 0) return <p className="muted">No payments yet. When you pay for a certificate it appears here.</p>;
  const shown = compact ? items.slice(0, 5) : items;
  return (
    <div className="scroll">
      <table className="pay-table">
        <thead><tr><th>Date</th><th>Course</th><th>Amount</th><th>Paid with</th><th>Status</th>{!compact && <th>Reference</th>}</tr></thead>
        <tbody>{shown.map(p => (
          <tr key={p.id}>
            <td>{when(p)}</td><td>{p.course}</td><td>₹{p.amount_inr}</td><td>{how(p)}</td>
            <td><span className={`pay-status ${p.status}`}>{LABEL[p.status] ?? p.status}</span>{p.status === "failed" && p.failure_reason ? <small className="block">{p.failure_reason}</small> : null}
              {p.status === "failed" && <small className="block"><Link to={`/courses/${p.course_slug}/pay`}>Try again</Link></small>}</td>
            {!compact && <td>{p.reference ?? "-"}</td>}
          </tr>))}</tbody>
      </table>
      {compact && items.length > 5 && <p><Link to="/payments">See all payments</Link></p>}
    </div>
  );
}

export function PaymentHistoryPage() {
  return (
    <section className="page">
      <h1>Payment history</h1>
      <PaymentHistory />
      <p><Link to="/dashboard">Back to my dashboard</Link></p>
    </section>
  );
}

/** Shown after a verified payment. If the confirmation is still on its way (webhook), it checks again for a few seconds. */
export function PaymentSuccess() {
  const { id = "" } = useParams();
  const [p, setP] = useState<Pay | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    http<Pay>(`/payments/${id}`).then(r => {
      if (!live) return; setP(r);
      if (r.status !== "verified" && r.status !== "in_review" && tries < 6) setTimeout(() => setTries(t => t + 1), 2000);
    }).catch(e => live && setErr(errText(e)));
    return () => { live = false; };
  }, [id, tries]);
  if (err) return <section className="page narrow"><p role="alert" className="err">{err}</p><Link to="/payments">Payment history</Link></section>;
  if (!p) return <section className="page narrow"><p aria-live="polite">Checking your payment…</p></section>;
  const ok = p.status === "verified";
  return (
    <section className="page narrow result-screen">
      <div className={`result-card ${ok ? "pass" : "wait"}`}>
        <div className="big-ico" aria-hidden="true">{ok ? "✅" : "⏳"}</div>
        <h1>{ok ? "Payment successful" : p.status === "in_review" ? "Payment submitted" : "Confirming your payment…"}</h1>
        <p>{ok ? `₹${p.amount_inr} received for the ${p.course} certificate.`
          : p.status === "in_review" ? "The admin will check the money in the bank account and confirm it. You will get a notification."
          : "This can take a few seconds. If money was deducted it will be confirmed automatically."}</p>
        {ok && <p className="muted">Payment id: {p.reference}</p>}
        <div className="row">
          {ok && p.certificate_issued && <Link className="solid" to="/certificates">Open my certificate</Link>}
          {ok && !p.certificate_issued && <Link className="solid" to={`/courses/${p.course_slug}`}>Back to the course</Link>}
          <Link className="ghost" to="/payments">Payment history</Link>
        </div>
      </div>
    </section>
  );
}

export function PaymentFailed() {
  const { id = "" } = useParams();
  const [p, setP] = useState<Pay | null>(null);
  useEffect(() => { http<Pay>(`/payments/${id}`).then(setP).catch(() => undefined); }, [id]);
  return (
    <section className="page narrow result-screen">
      <div className="result-card fail">
        <div className="big-ico" aria-hidden="true">❌</div>
        <h1>Payment failed</h1>
        <p>{p?.failure_reason || "The payment was not completed. No certificate was issued."}</p>
        <p className="muted">If money was deducted from your account, the bank returns it automatically, usually within 5 to 7 days. If the payment was in fact captured, it is confirmed here automatically.</p>
        <div className="row">
          <Link className="solid" to={p?.course_slug ? `/courses/${p.course_slug}/pay` : "/courses"}>Try again</Link>
          <Link className="ghost" to="/payments">Payment history</Link>
        </div>
      </div>
    </section>
  );
}


