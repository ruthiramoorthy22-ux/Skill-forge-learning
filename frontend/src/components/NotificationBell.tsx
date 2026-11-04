import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { http } from "../api";
import { useAuth } from "../auth";

/** Bell with the number of unread notifications. It checks again every minute while a student is signed in. */
export default function NotificationBell() {
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!user || user.role === "admin") { setUnread(0); return; }
    const load = () => http<{ unread: number }>("/me/notifications").then(r => setUnread(r.unread)).catch(() => undefined);
    load();
    const t = setInterval(load, 60000);
    window.addEventListener("sf-notifications", load);
    return () => { clearInterval(t); window.removeEventListener("sf-notifications", load); };
  }, [user?.id, user?.role]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!user || user.role === "admin") return null;
  return (
    <Link className="bell" to="/notifications" aria-label={unread ? `${unread} unread notifications` : "Notifications"}>
      <span aria-hidden="true">🔔</span>{unread > 0 && <span className="bell-n">{unread > 9 ? "9+" : unread}</span>}
    </Link>
  );
}
