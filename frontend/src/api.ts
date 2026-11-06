export type Level = "beginner" | "intermediate" | "advanced";
export interface Course {
  slug: string; title: string; category_id: string; category_name: string;
  level: Level; status: "planned" | "in_development" | "available"; lesson_count?: number;
  is_free?: boolean; price_inr?: number;   // price_inr is 0 for a free course
}
export interface Category { id: string; name: string; course_count: number }
export interface Paged<T> { items: T[]; total: number; page: number; page_size: number }
export interface User { id: string; email: string; display_name: string; role: "student" | "admin"; created_at: string; token?: string }

export interface Outline { title: string; lessons: { slug: string; title: string }[] }
export interface CourseDetail extends Course {
  lesson_count: number; summary?: string; objectives?: string[]; est_minutes?: number; outline: Outline[] | null;
}
export interface Progress { enrolled: boolean; completed: string[]; total: number; percent: number; last_lesson: string | null; course_completed?: boolean }
export interface LessonData {
  slug: string; title: string; module_title: string; body_md: string; example_code: string;
  example_lang: string; expected_output: string; completed: boolean; prev: string | null; next: string | null;
}
export interface EnrollmentRow {
  course_slug: string; title: string; level: Level; total: number; completed: number; percent: number;
  last_lesson: string | null; enrolled_at: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

const w = window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } };
/** True when running inside the Android app (Capacitor). */
export const isApp = !!w.Capacitor?.isNativePlatform?.();
/** Server address for the Android app, set at build time in .env.app (the website uses relative URLs). */
export const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/$/, "");
const TOKEN_KEY = "sf_token";
let token: string | null = null;
try { token = isApp ? localStorage.getItem(TOKEN_KEY) : null; } catch { token = null; }
export function setToken(t: string | null) {
  token = t;
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

async function request<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  if (isApp && !API_BASE) throw new ApiError(0, "The server address is not set. Put it in frontend/.env.app and rebuild the app.");
  const headers: Record<string, string> = {};
  if (opts.body) headers["Content-Type"] = "application/json";
  if (isApp) { headers["X-Client"] = "app"; if (token) headers["Authorization"] = `Bearer ${token}`; }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api${path}`, {
      method: opts.method ?? "GET", headers, body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: isApp ? "omit" : "include",
    });
  } catch {
    throw new ApiError(0, isApp ? "Cannot reach the server. Check your internet connection and the server address." : "Cannot reach the server.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (res.status === 422) msg = "Check the form: use a valid email and a password of at least 10 characters.";
    } catch { /* keep default message */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

const withToken = (u: User) => { if (u.token) setToken(u.token); return u; };

export const api = {
  categories: () => request<{ items: Category[] }>("/categories"),
  courses: (qs: string) => request<Paged<Course>>(`/courses?${qs}`),
  projects: () => request<{ items: { slug: string; title: string; level: string; summary: string; body_md: string; status: string }[] }>("/projects"),
  me: () => request<User>("/auth/me"),
  register: (b: { email: string; display_name: string; password: string }) => request<User>("/auth/register", { method: "POST", body: b }).then(withToken),
  login: (b: { email: string; password: string }) => request<User>("/auth/login", { method: "POST", body: b }).then(withToken),
  adminLogin: (b: { email: string; password: string }) => request<User>("/auth/admin/login", { method: "POST", body: b }).then(withToken),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }).finally(() => setToken(null)),
  updateProfile: (display_name: string) => request<User>("/me", { method: "PATCH", body: { display_name } }),
  courseDetail: (slug: string) => request<CourseDetail>(`/courses/${slug}`),
  courseProgress: (slug: string) => request<Progress>(`/courses/${slug}/progress`),
  enroll: (slug: string) => request<Progress>(`/courses/${slug}/enroll`, { method: "POST" }),
  lesson: (slug: string, lesson: string) => request<LessonData>(`/courses/${slug}/lessons/${lesson}`),
  completeLesson: (slug: string, lesson: string) => request<Progress>(`/courses/${slug}/lessons/${lesson}/complete`, { method: "POST" }),
  myEnrollments: () => request<{ items: EnrollmentRow[] }>("/me/enrollments"),
  adminOverview: () => request<{ total_students: number }>("/admin/overview"),
};

export const statusLabel: Record<Course["status"], string> = {
  planned: "Planned",
  in_development: "Lessons in development",
  available: "Available",
};

export const http = request;
export const errText = (e: unknown, fallback = "Something went wrong.") => (e instanceof Error ? e.message : fallback);

/** Opens a certificate download. A 5-minute link for that one certificate is requested first, so it also works in the Android app. */
export async function openCertificate(certificateId: string, format: "pdf" | "png") {
  const { url } = await request<{ url: string }>(`/certificates/${certificateId}/link?format=${format}`, { method: "POST" });
  const full = API_BASE + url;
  if (isApp) { const { Browser } = await import("@capacitor/browser"); await Browser.open({ url: full }); }
  else window.open(full, "_blank", "noopener");
}
