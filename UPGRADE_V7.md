# SkillForge v7 upgrade (payments, per-course pricing, notifications, profile picture, certificate designs)

## What changed
Backend (backend/app): `routes_pay.py` (new), `routes_notify.py` (new), `routes_templates.py` (new), `notify.py` (new), `certificate_image.py` (rewritten),
`certificates.py`, `routes_certs.py`, `payments.py`, `app_settings.py`, `models.py`, `main.py`, `routes_admin.py`, `routes_admin_extra.py`,
`routes_student.py`, `routes_learning.py`, `config.py`. New assets: `assets/certificate_default.png`, `assets/fonts/SourceSerif_*.ttf`
(Source Serif, SIL OFL). Removed: `assets/certificate_template.png` (old certificate). `requirements.txt` + `psycopg[binary]` for PostgreSQL.
Frontend (frontend/src): new `pages/Payments.tsx`, `pages/Notifications.tsx`, `pages/AdminDesign.tsx`, `components/Avatar.tsx`, `components/NotificationBell.tsx`;
edited `App.tsx`, `pages/ResultPay.tsx`, `CourseDetail.tsx`, `Catalog.tsx`, `Dashboard.tsx`, `Profile.tsx`, `AppHome.tsx`, `Admin.tsx`, `AdminExtra.tsx`, `components/Drawer.tsx`, `ProjectSubmit.tsx`, `api.ts`, `app.css`.
Tests: `tests/test_payments_v7.py` (new, 16 tests); 5 old test expectations updated. Total 121 pass.

New database columns/tables are created automatically at startup (no manual migration):
courses.is_paid / price_inr / project_title / project_description, payments.method / failure_reason / note / created_at, student_profiles.avatar,
tables payment_webhook_events, user_notifications, certificate_templates. Existing courses stay PAID at the default price.
