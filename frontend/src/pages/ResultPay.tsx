import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { API_BASE, errText, http, openCertificate } from "../api";
import { loadRazorpay } from "../razorpay";

interface FR { state: "none" | "pending" | "released"; score_pct?: number; passed?: boolean; pass_mark?: number }
interface Cert { price_inr: number; is_free?: boolean; can_pay?: boolean; payments_configured: boolean; course_completed: boolean; paid: boolean; awaiting_admin?: boolean; issued: boolean; certificate_id: string | null; locked_reason: string | null }
interface Order { order_id: string; amount: number; currency: string; key_id: string; course_title: string; student_name: string; student_email: string; brand: string }
interface Methods { brand: string; razorpay: { enabled: boolean; mode: string; hide: string[]; methods: string[] }; upi: { enabled: boolean; upi_id: string; payee_name: string } }
interface UpiOrder { payment_id: string; amount: number; upi_id: string; payee_name: string; uri: string }

/** Final exam result. Students see it only after the admin releases it. A passed result has a Next button that leads to payment. */
export function FinalResultPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  const [r, setR] = useState<FR | null>(null);
  const [finalId, setFinalId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { setErr(null); http<FR>(`/courses/${slug}/final-result`).then(setR).catch(e => setErr(errText(e))); }, [slug]);
  useEffect(() => {
    load();
    http<{ items: { id: number; kind: string }[] }>(`/courses/${slug}/quizzes`).then(q => setFinalId(q.items.find(i => i.kind === "final")?.id ?? null)).catch(() => undefined);
  }, [load, slug]);

  if (err) return <section className="page narrow"><p role="alert" className="err">{err}</p><Link to={`/courses/${slug}`}>Back to the course</Link></section>;
  if (!r) return <section className="page narrow"><p aria-live="polite">Loading…</p></section>;
  return (
    <section className="page narrow result-screen">
      {r.state === "none" && (<><h1>No result yet</h1><p>You have not taken the final exam yet.</p><Link className="solid" to={`/courses/${slug}`}>Back to the course</Link></>)}
      {r.state === "pending" && (
        <div className="result-card wait">
          <div className="big-ico" aria-hidden="true">⏳</div>
          <h1>Waiting for your result</h1>
          <p>Your final exam is submitted. The admin will check it and release your result. It will appear here.</p>
          <div className="row"><button className="solid" onClick={load}>Check again</button><Link className="ghost" to="/home">Home</Link></div>
        </div>
      )}
      {r.state === "released" && (
        <div className={`result-card ${r.passed ? "pass" : "fail"}`}>
          <div className="big-ico" aria-hidden="true">{r.passed ? "🎉" : "💪"}</div>
          <h1>{r.passed ? "You passed!" : "Not passed this time"}</h1>
          <p className="score">{r.score_pct}%</p>
          <p className="muted">Pass mark {r.pass_mark}%</p>
          {r.passed ? (
            <button className="solid big wide" onClick={() => nav(`/courses/${slug}/pay`)}>Next</button>
          ) : (
            <><p>Revise the lessons and try the final exam again.</p>
              {finalId && <Link className="solid big wide" to={`/quizzes/${finalId}`}>Retake the final exam</Link>}</>
          )}
        </div>
      )}
    </section>
  );
}

/** Pay screen. After a verified payment the certificate is released. The admin decides which methods appear. */
export function PayPage() {
  const { slug = "" } = useParams();
  const nav = useNavigate();
  const [cert, setCert] = useState<Cert | null>(null);
  const [methods, setMethods] = useState<Methods | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [upi, setUpi] = useState<UpiOrder | null>(null);
  const [utr, setUtr] = useState("");
  const load = useCallback(() => { http<Cert>(`/courses/${slug}/certificate`).then(setCert).catch(e => setNote(errText(e))); }, [slug]);
  useEffect(load, [load]);
  useEffect(() => { http<Methods>("/payments/methods").then(setMethods).catch(() => undefined); }, []);

  async function payRazorpay() {
    setBusy(true); setNote(null);
    try {
      const order = await http<Order>(`/courses/${slug}/certificate/order`, { method: "POST" });
      await loadRazorpay();
      let done = false, failedReason = "";
      const hide = (methods?.razorpay.hide ?? []).map(method => ({ method }));
      const rzp = new window.Razorpay!({
        key: order.key_id, amount: order.amount, currency: order.currency, order_id: order.order_id,
        name: order.brand, description: `${order.course_title} certificate`,
        prefill: { name: order.student_name, email: order.student_email }, theme: { color: "#0b6b5e" },
        ...(hide.length ? { config: { display: { hide } } } : {}),
        handler: async (resp: Record<string, string>) => {
          done = true;
          try { await http("/payments/razorpay/verify", { method: "POST", body: resp }); nav(`/payment/success/${order.order_id}`); }
          catch (e) {
            // The gateway may still be confirming: the success page checks again for a few seconds.
            if (e instanceof Error && /confirmed automatically/.test(e.message)) nav(`/payment/success/${order.order_id}`);
            else { setNote(errText(e)); setBusy(false); }
          }
        },
        modal: { ondismiss: () => {
          if (done) return;
          if (failedReason) nav(`/payment/failed/${order.order_id}`);
          else { setNote("Payment cancelled. You were not charged."); setBusy(false); }
        } },
      });
      rzp.on("payment.failed", (r: unknown) => {
        const d = (r as { error?: { description?: string } })?.error?.description ?? "The payment failed.";
        failedReason = d;
        http("/payments/razorpay/failed", { method: "POST", body: { razorpay_order_id: order.order_id, reason: d } }).catch(() => undefined);
      });
      rzp.open();
    } catch (e) { setNote(errText(e)); setBusy(false); }
  }

  async function startUpi() {
    setBusy(true); setNote(null);
    try { setUpi(await http<UpiOrder>(`/courses/${slug}/certificate/upi-order`, { method: "POST" })); }
    catch (e) { setNote(errText(e)); } finally { setBusy(false); }
  }
  async function submitUtr() {
    if (!upi) return;
    setBusy(true); setNote(null);
    try { await http(`/payments/upi/${upi.payment_id}/submit`, { method: "POST", body: { utr: utr.trim() } }); nav(`/payment/success/${upi.payment_id}`); }
    catch (e) { setNote(errText(e)); setBusy(false); }
  }

  if (!cert) return <section className="page narrow">{note ? <p role="alert" className="err">{note}</p> : <p aria-live="polite">Loading…</p>}</section>;
  const canRzp = !!methods?.razorpay.enabled, canUpi = !!methods?.upi.enabled;
  return (
    <section className="page narrow result-screen">
      <h1>Get your certificate</h1>
      <div className="cert-preview locked-soft"><img src={`${API_BASE}/api/courses/${slug}/certificate/preview`} alt="Sample certificate" /></div>
      {cert.issued ? (
        <div className="result-card pass">
          <div className="big-ico" aria-hidden="true">🏅</div>
          <h2>Your certificate is ready</h2>
          <div className="row">
            <button className="solid" onClick={() => openCertificate(cert.certificate_id!, "pdf").catch(e => setNote(errText(e)))}>Download PDF</button>
            <button className="ghost" onClick={() => openCertificate(cert.certificate_id!, "png").catch(e => setNote(errText(e)))}>Download image</button>
          </div>
        </div>
      ) : !cert.course_completed ? (
        <><p>{cert.locked_reason}</p><Link className="solid" to={`/courses/${slug}/result`}>See my result</Link></>
      ) : cert.awaiting_admin ? (
        <p><strong>✅ {cert.is_free ? "Course completed." : "Payment received."}</strong> Your certificate will be released shortly.</p>
      ) : cert.is_free ? (
        <><p><strong>This course is free.</strong> No payment is needed.</p><button className="solid big wide" onClick={load}>Get my certificate</button></>
      ) : !canRzp && !canUpi ? (
        <p>Online payment is not available right now. Please try again later.</p>
      ) : (
        <>
          <p>Your course is complete. Pay <strong>₹{cert.price_inr}</strong> once to get your certificate.</p>
          {canRzp && (
            <div className="pay-opt">
              <h3>Pay online</h3>
              <p className="muted">UPI (Google Pay, PhonePe, Paytm), cards and net banking{methods?.razorpay.mode === "test" ? " · TEST MODE: no real money" : ""}</p>
              <button className="solid big wide" onClick={payRazorpay} disabled={busy}>{busy && !upi ? "Please wait…" : `Pay now ₹${cert.price_inr}`}</button>
            </div>
          )}
          {canUpi && (
            <div className="pay-opt">
              <h3>Pay by UPI directly</h3>
              <p className="muted">Pay to our UPI id from any UPI app, then enter the 12-digit UTR number. The admin confirms it.</p>
              {!upi ? <button className={canRzp ? "ghost wide" : "solid big wide"} onClick={startUpi} disabled={busy}>Pay ₹{cert.price_inr} by UPI</button> : (
                <div className="card">
                  <p>Pay <strong>₹{upi.amount}</strong> to <strong>{upi.upi_id}</strong> ({upi.payee_name})</p>
                  <div className="row">
                    <a className="solid" href={upi.uri}>Open Google Pay / PhonePe</a>
                    <button className="ghost" onClick={() => navigator.clipboard?.writeText(upi.upi_id).then(() => setNote("UPI id copied."))}>Copy UPI id</button>
                  </div>
                  <label>UTR / reference number (12 digits, shown in your UPI app after paying)
                    <input inputMode="numeric" pattern="\d{12}" maxLength={12} value={utr} onChange={e => setUtr(e.target.value.replace(/\D/g, ""))} placeholder="412345678901" /></label>
                  <button className="solid" onClick={submitUtr} disabled={busy || utr.length !== 12}>I have paid, submit</button>
                </div>)}
            </div>
          )}
        </>
      )}
      {note && <p role="status">{note}</p>}
      <p><Link to={`/courses/${slug}`}>Back to the course</Link> · <Link to="/payments">Payment history</Link></p>
    </section>
  );
}
