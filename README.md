# Skill Learning (web app, Android app, admin, certificates)

Backend: FastAPI + SQLAlchemy. Frontend: React + TypeScript (Vite). Android: the same frontend wrapped with Capacitor.
Interactive API docs: http://localhost:8000/docs (while the backend runs).

## What changed in v6
- **App name is now "Skill Learning"** (app title, Android launcher name, header). The package id `com.skillforge.learning` is unchanged so an installed build can be updated.
- **New app look**: sign-in screen with a welcome illustration, Home screen (greeting, hero card, four quick actions, overall progress ring, your courses), and a **side menu** (hamburger button on Home) with Profile, Courses, My results, My certificates, My progress, Help, dark mode and Sign out.
- **Only 4 bottom tabs**: Home, Courses, Practice, Profile.
- **Profile** has School name, **10th mark** and **12th mark** (percentage like 88.4, or marks/total like 442/500). The admin sees and edits them in Students > Details and in the CSV export.
- **Certificate no longer prints the project name.** The project step stays **on**: after Next, the student submits the project, the admin approves it, then the student pays.
- **Final exam result is hidden from the student.** After the final exam the student only sees "submitted". The admin gets a notification and opens **Admin > Final results** to see the score and press **Release result**.
- **After release**: the student opens the result, presses **Next** (if passed), pays on the **Pay** screen, and the certificate is released (automatically, or after your unlock if Settings says so). A failed result shows **Retake the final exam**.
- Existing databases are upgraded automatically on start (new columns are added; old exam results stay visible).
- Backend tests were updated for the hidden-result flow. **They were not run here** (the build environment had no Python packages or internet). Run `pytest` in `backend` and tell me what fails.
- The Google sign-in button from your reference screenshot is **not included** (it needs a Google Cloud OAuth client). The login still uses email, not a username.

## What changed in v5
- **Project submission**: after the final exam the student submits a project (name, description, GitHub and demo links). The admin gets a notification, opens **Admin > Submissions**, and approves, requests changes (with feedback), or approves and unlocks the certificate at once. The student pays only after approval. Admin can switch the project requirement off in Settings.
- **Certificate** keeps the same design and now prints `Project: <name>` above the date.
- **Student profile** page (`/profile`): name, phone, city, college, degree, year, school. Saved on the server. The name is locked once a certificate exists.
- **Admin edits every student detail** (Students > Details). Phone and college show in the student table and the CSV export. Every edit is in the audit log.
- **Professional look**: Inter font, blue/slate palette, soft cards, clean tables, admin sidebar on desktop.
- Admin tab "Projects" is now **Project Ideas** (the guided project list); student work is under **Submissions**.

## What changed in v4
- **AI tutor/chatbot removed** (backend route, database model, settings and the lesson-page box).
- **One certificate price for all courses (default Rs 55), editable by the admin** in Admin > Settings. Admin can also choose: certificate issued automatically after payment, **or kept locked until the admin unlocks it**.
- **Admin unlock**: Admin > Certificates > "Waiting for unlock" lists students who finished a course. Unlock (paid or not), or Unlock and email (needs SMTP). Admin still gets a notification on every payment.
- **Admin can add / edit / delete everything**: courses (edit details, delete), modules (rename, delete), lessons, topic tests / practice / final exams (and their questions), **coding challenges** (full form with test cases), **projects** (new, stored in the database). Deleting a course that has paid certificates is refused (unpublish it instead).
- **SoloLearn-style app look**: bottom tab bar on phones, lesson screen with segmented progress and a big Continue button, course page as a lesson path, big tappable quiz answers.
- **Locked demo certificate** at the end of every course page (sample with a placeholder name, blurred with a lock until the student earns it).
- `requirements.txt` was missing `numpy` and `pillow`, which the certificate renderer needs. Added.

## What works (tested with 105 automated backend tests and a live-server run)
- Accounts, student dashboard, admin login (role checked on the server), rate limits, audit logs.
- Courses with original lessons for **Python (5), HTML5 (3), CSS3 (3)** only. Every other catalog course is still "planned".
- **Topic tests, practice sets and a locked final exam.** The final exam opens only after every lesson is done and every topic test has been attended (`FINAL_UNLOCK_RULE=attempted`, or `passed` to require passing them). Practice is free, optional, unlimited and never affects results, XP or completion.
- **Admin controls everything about tests:** add, edit and delete questions (single, multiple, short answer), create topic tests / practice / final exams per course, publish or unpublish, view each course's tests inside its page.
- **Certificate** (your design, same for every course; only name, course and date change): locked until the course is completed (all lessons + final exam passed) **and** the Razorpay payment is verified on the server. Students download PDF/PNG. The name is locked after issue.
- **Admin notification** on every verified payment (in the dashboard bell and, if SMTP is set, by email to the admin). Admin > Certificates: download, **Send email** (if SMTP is set) or **Mark as sent** after emailing it yourself.
- Admin payments page and revenue (verified payments only), analytics, student table, live activity.
- **Android app** project (Capacitor): opens on the sign-in page.

## NOT verified here (be aware)
- **The new screens (course path, lesson screen, bottom bar, admin forms) compile and the API behind them is tested, but nobody looked at them in a browser or on a phone.** Expect small spacing/colour fixes.
- **Razorpay was never called for real.** Order creation, the checkout window and the webhook are written to Razorpay's documented API and the signature check is tested, but this build environment cannot reach api.razorpay.com. Do a test-mode payment yourself (test card from Razorpay docs) before trusting it.
- **The Android app was not compiled or run.** The Android project is generated and the web part builds, but no APK was built (no Android SDK here). Razorpay's web checkout inside an Android WebView can limit some UPI app-switching; Razorpay's native Android SDK is the more robust option for production.
- Judge0 code execution still needs your own service (see below). No frontend automated tests. No browser/phone click-through was done.
- Not built: lessons for Java, JavaScript, DSA and other courses (the admin can now write them in the Courses tab); study-material uploads; password reset and email verification; PostgreSQL/Alembic migrations; Tamil or other non-Latin characters on the certificate (the font supports Latin, Greek and Cyrillic only).

## Run the website (Windows PowerShell, two terminals)
    cd backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

    cd frontend
    npm install
    npm run dev                 # open http://localhost:5173

Admin account (once, from `backend`): `python -m app.create_admin` then sign in at `/admin/login`.

## Payments (Razorpay test mode)
1. In `backend`, copy `.env.example` to `.env`.
2. Set `RAZORPAY_KEY_ID` (the public key, starts with rzp_test_) and `RAZORPAY_KEY_SECRET` (the secret).
   **Never put the secret in the frontend, in this README, in a chat, or in a git repo.** If it was ever shared, regenerate it in the Razorpay dashboard.
3. The certificate price is **Rs 55 for every course** and is changed by the admin in **Admin > Settings** (`CERTIFICATE_PRICE_INR` is only the first-run default).
4. Restart the backend. The course page then shows "Pay and get the certificate" once a student completes the course.
5. Optional webhook (backup confirmation): in Razorpay dashboard add `https://YOUR-SERVER/api/payments/razorpay/webhook`, event `payment.captured`, and put the webhook secret in `RAZORPAY_WEBHOOK_SECRET`. It needs a public HTTPS address.
Going live later: switch to live keys, and complete Razorpay KYC.

## Email (admin alerts and sending certificates)
Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` in `backend/.env`. For Gmail use smtp.gmail.com, port 587 and an **App Password** (needs 2-step verification), not your normal password. Without SMTP the dashboard bell still works and you email certificates yourself, then click **Mark as sent**.

## Build the Android app
Prerequisites: Android Studio (includes JDK 17), Node 18+, and the backend reachable from the phone.
1. Backend for the phone (same Wi-Fi test): `uvicorn app.main:app --host 0.0.0.0 --port 8000`, and allow port 8000 in Windows Firewall.
2. In `frontend`: copy `.env.app.example` to `.env.app` and set `VITE_API_BASE` to `http://<your PC IPv4>:8000` (find it with `ipconfig`). Android emulator: `http://10.0.2.2:8000`.
3. `npm install`, then `npm run app:sync` (builds the web part for the app and copies it into the Android project), then `npm run app:open` (opens Android Studio).
4. Wait for Gradle sync, press Run on a phone or emulator, or Build > Build APK(s).
5. Release build: use an **https** server address, run with `CAP_RELEASE=1` set (PowerShell: `$env:CAP_RELEASE=1`) before `npm run app:sync`, and sign the APK in Android Studio. The app signs in with a bearer token stored on the phone.
Every time you change the frontend, run `npm run app:sync` again.

## Using the new features (admin)
- Courses > a course > **Manage lessons**: modules, lessons, and the list of that course's topic tests, practice and final exam with Edit / Delete for each question.
- Quizzes tab: create a **Topic test**, **Practice** or **Final exam** with questions; publish when ready.
- Students see: topic tests and practice (open once enrolled), the final exam (locked with the reason), then the certificate card (locked, then pay, then download).

## External services still optional
- Judge0 for the playground/challenges: `JUDGE0_URL` (see `.env.example`).

## Tests
    cd backend
    python -m pytest            # 105 tests

## Security notes
Passwords hashed (Argon2). Web uses an HttpOnly cookie; the app uses a Bearer token (returned only when the `X-Client: app` header is sent). Payment confirmation is checked with Razorpay's HMAC signature on the server; browser success messages are never trusted; a payment id can be used once. Certificates download only for their owner or an admin, or through a 5-minute single-certificate link. Secrets are read only from environment variables. Keep `backend/.env` out of git.
Cleartext HTTP is allowed in the default (test) Android build so a phone can reach your PC; use the release build with https for real users.
