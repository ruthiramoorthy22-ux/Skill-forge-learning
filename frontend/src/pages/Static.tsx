import { ReactNode, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { api, Category } from "../api";

const Page = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="page"><h1>{title}</h1>{children}</section>
);


export const About = () => (
  <Page title="About Skill Forge Learning">
    <div className="policy-content">

      <h2>Welcome to Skill Forge Learning!</h2>

      <p>
        Skill Forge Learning is an online programming and
        technology education platform designed to help students
        develop coding knowledge, practical skills and confidence
        through structured learning.
      </p>

      <p>
        Our platform provides original lessons, interactive
        exercises, quizzes, examinations and practical learning
        resources to make programming education accessible
        and effective.
      </p>

      <h2>Our Mission</h2>
      <p>
        Our mission is to make programming education simple,
        accessible and practical for everyone. We aim to help
        learners build strong technical foundations and
        develop the skills needed for the technology industry.
      </p>

      <h2>Our Vision</h2>
      <p>
        Our vision is to become a trusted learning platform
        where students can learn new technologies, improve
        their coding abilities and transform their ideas
        into real-world projects.
      </p>

      <h2>What We Offer</h2>
      <ul>
        <li>Structured programming courses.</li>
        <li>Step-by-step lessons and explanations.</li>
        <li>Programming exercises and practice activities.</li>
        <li>Topic-wise quizzes and assessments.</li>
        <li>Final course examinations.</li>
        <li>Optional practical projects.</li>
        <li>Course completion certificates.</li>
        <li>Personal learning progress tracking.</li>
      </ul>

      <h2>Our Learning Approach</h2>
      <p>
        We believe that learning programming requires both
        theoretical understanding and practical experience.
        Our structured learning approach helps students
        progress from fundamental concepts to advanced topics.
      </p>

      <h2>Who Can Learn?</h2>
      <p>
        Skill Forge Learning is designed for beginners,
        college students, aspiring developers and anyone
        interested in learning programming and technology.
      </p>

      <h2>Our Commitment</h2>
      <p>
        We are committed to continuously improving our
        educational content, platform experience and
        learning resources to support students in their
        technical learning journey.
      </p>

      <h2>Our Motto</h2>
      <p>
        <strong>Learn. Practice. Build. Achieve.</strong>
      </p>

      <h2>Contact Us</h2>
      <p>
        Have questions or suggestions? We would love to
        hear from you.
      </p>
      <p>
        <strong>Email:</strong>{" "}
        <a href="mailto:skillforgelearning22@gmail.com">
          skillforgelearning22@gmail.com
        </a>
      </p>

      <p>
        <strong>Skill Forge Learning</strong>
        <br />
        Empowering learners through technology and education.
      </p>

    </div>
  </Page>
);


export function Paths() {
  const [cats, setCats] = useState<Category[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api.categories().then(r => setCats(r.items)).catch(() => setErr(true)); }, []);
  return (
    <Page title="Learning paths">
      <p className="muted">Each path groups courses from beginner to advanced. All paths are planned; lessons are not published yet.</p>
      {err && <p role="alert" className="err">Could not load paths. Check that the backend is running.</p>}
      {!cats && !err && <p>Loading paths…</p>}
      <ul className="grid">
        {cats?.map(c => (
          <li key={c.id} className="card">
            <h3>{c.name}</h3>
            <p className="muted">{c.course_count} planned courses</p>
            <Link to={`/courses`}>Browse courses</Link>
          </li>
        ))}
      </ul>
    </Page>
  );
}

export function Projects() {
  const [items, setItems] = useState<{ slug: string; title: string; level: string; summary: string; body_md: string; status: string }[] | null>(null);
  const [err, setErr] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { api.projects().then(r => setItems(r.items)).catch(() => setErr(true)); }, []);
  return (
    <Page title="Projects">
      <p className="muted">Build real things step by step. Projects marked Planned are coming soon.</p>
      {err && <p role="alert" className="err">Could not load projects. Check that the backend is running.</p>}
      {!items && !err && <p>Loading projects…</p>}
      <ul className="grid">{items?.map(p => (
        <li key={p.slug} className="card">
          <h3>{p.title}</h3>
          <p className="muted">{p.summary}</p>
          <p><span className={`tag ${p.level}`}>{p.level}</span> {p.status === "planned" && <span className="tag">Planned</span>}</p>
          {p.status === "available" && <button className="ghost" onClick={() => setOpen(open === p.slug ? null : p.slug)}>{open === p.slug ? "Hide steps" : "Open project"}</button>}
          {open === p.slug && <div className="md"><ReactMarkdown>{p.body_md}</ReactMarkdown></div>}
        </li>))}</ul>
    </Page>
  );
}

export const Help = () => (
 <Page title="Help & Support">
  <h2>Welcome to Skill Forge Learning Support!</h2>

  <p>
    We are here to help you with your learning journey.
    If you face any problems, please contact our support team.
  </p>

  <h3>📚 Courses & Learning</h3>
  <p>Get help with course enrollment, lessons and learning progress.</p>

  <h3>📝 Exams & Results</h3>
  <p>Get assistance with topic tests, final exams and results.</p>

  <h3>🏆 Certificates</h3>
  <p>Get help with certificate eligibility, payments and downloads.</p>

  <h3>💳 Payment Support</h3>
  <p>Need help with failed payments or payment verification?</p>

  <h3>🔐 Account & Login</h3>
  <p>Get assistance with login, registration and password reset.</p>

  <h3>📩 Contact Us</h3>
  <p>
    Email:{" "}
    <a href="mailto:skillforgelearning22@gmail.com">
      skillforgelearning22@gmail.com
    </a>
  </p>

  <p>
    Please include your registered email address and a
    description of your issue when contacting us.
  </p>

  <h3>Our Mission</h3>
  <p>
    Learn. Practice. Build. Achieve.
    <br />
    Thank you for choosing Skill Forge Learning!
  </p>
</Page>
);


export const Privacy = () => (
  <Page title="Privacy Policy">
    <div className="policy-content">

      <p>
        <strong>Last Updated:</strong> November 6, 2026
      </p>

      <h2>1. Introduction</h2>
      <p>
        Welcome to Skill Forge Learning. We respect your privacy
        and are committed to protecting your personal information.
        This Privacy Policy explains how we collect, use, store
        and protect information when you use our educational platform.
      </p>

      <h2>2. Information We Collect</h2>
      <p>We may collect the following information:</p>
      <ul>
        <li>Full Name</li>
        <li>Email Address</li>
        <li>Account Login Information</li>
        <li>Course Enrollment Details</li>
        <li>Learning Progress and Completed Lessons</li>
        <li>Quiz and Examination Results</li>
        <li>Certificate Information</li>
        <li>Payment Transaction References and Status</li>
        <li>Support Requests and Messages</li>
      </ul>

      <h2>3. How We Use Your Information</h2>
      <p>We use collected information to:</p>
      <ul>
        <li>Create and manage student accounts.</li>
        <li>Provide access to courses and learning materials.</li>
        <li>Save course progress and examination results.</li>
        <li>Generate course completion certificates.</li>
        <li>Process and verify certificate payments.</li>
        <li>Provide technical support.</li>
        <li>Improve our platform and user experience.</li>
        <li>Protect accounts against unauthorized access.</li>
      </ul>

      <h2>4. Payment Information</h2>
      <p>
        Skill Forge Learning uses Razorpay for payment processing.
        Payment transactions are handled through Razorpay and
        its applicable security procedures.
      </p>
      <p>
        We may receive transaction references, payment status
        and related information required to verify payments.
        We do not intend to store students' card PINs,
        UPI PINs or banking passwords.
      </p>
      <p>
        Payment processing is subject to Razorpay's own
        privacy policy and terms.
      </p>

      <h2>5. Data Protection and Security</h2>
      <p>
        We take reasonable technical and organizational measures
        to protect personal information from unauthorized access,
        loss, misuse or disclosure.
      </p>
      <p>
        However, no internet-based system can guarantee
        absolute security.
      </p>

      <h2>6. Information Sharing</h2>
      <p>
        We do not sell students' personal information.
        Information may be shared with trusted service providers
        when necessary to operate the platform, process payments,
        provide hosting or deliver support services.
      </p>
      <p>
        Information may also be disclosed when required
        by applicable law.
      </p>

      <h2>7. Data Retention</h2>
      <p>
        We retain personal information for as long as necessary
        to provide our services, maintain student accounts,
        preserve learning records, verify payments and meet
        applicable legal obligations.
      </p>

      <h2>8. Student Rights</h2>
      <p>
        Students may request access to, correction of or
        deletion of their personal information, subject to
        applicable legal requirements and necessary record
        retention obligations.
      </p>
      <p>
        For privacy-related requests, contact our support team.
      </p>

      <h2>9. Cookies and Sessions</h2>
      <p>
        Our platform may use cookies or similar technologies
        to maintain login sessions, improve security and
        support essential website functionality.
      </p>

      <h2>10. Third-Party Services</h2>
      <p>
        Our platform may use third-party services such as
        Razorpay, hosting providers and other technical
        service providers. Their privacy practices are
        governed by their respective policies.
      </p>

      <h2>11. Children's Privacy</h2>
      <p>
        Our platform is intended for individuals who are
        legally permitted to use the service. Where applicable,
        parental or guardian consent must be obtained before
        collecting personal information from children.
      </p>

      <h2>12. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy from time to time.
        Updated versions will be published on this page
        with a revised Last Updated date.
      </p>

      <h2>13. Contact Us</h2>
      <p>
        For privacy questions or requests, contact:
      </p>
      <p>
        <strong>Skill Forge Learning</strong>
        <br />
        Email: skillforgelearning22@gmail.com
      </p>

    </div>
  </Page>
);

export const Terms = () => (
  <Page title="Terms of Service">
    <div className="policy-content">

      <p>
        <strong>Last Updated:</strong> November 6, 2026
      </p>

      <h2>1. Acceptance of Terms</h2>
      <p>
        Welcome to Skill Forge Learning. By accessing or using
        our website and educational services, you agree to
        these Terms of Service. If you do not agree, please
        discontinue using the platform.
      </p>

      <h2>2. About Our Platform</h2>
      <p>
        Skill Forge Learning is an online programming and
        technical education platform designed to help students
        learn programming through courses, lessons, practice,
        projects and examinations.
      </p>

      <h2>3. Student Accounts</h2>
      <ul>
        <li>Students must provide accurate registration details.</li>
        <li>Students are responsible for keeping their passwords secure.</li>
        <li>Account credentials must not be shared with unauthorized users.</li>
        <li>Students must notify us if they suspect unauthorized account access.</li>
        <li>Students are responsible for activities performed through their accounts.</li>
      </ul>

      <h2>4. Courses and Learning Materials</h2>
      <p>
        Course materials, lessons, quizzes and learning resources
        are provided for educational purposes.
      </p>
      <p>
        Students may access available courses according to
        their account permissions and applicable course rules.
      </p>

      <h2>5. Projects and Practice</h2>
      <p>
        Projects and practice activities are provided to improve
        programming knowledge and practical skills.
      </p>
      <p>
        Project participation is optional unless a specific
        activity is explicitly identified as a requirement
        for that activity.
      </p>

      <h2>6. Examinations and Results</h2>
      <ul>
        <li>Students must complete the required course lessons.</li>
        <li>Students must complete the applicable final examination.</li>
        <li>Students must follow examination instructions.</li>
        <li>Exam results are recorded in the student account.</li>
        <li>Passing requirements are determined by the applicable course assessment rules.</li>
      </ul>

      <h2>7. Certificate Eligibility</h2>
      <p>
        Certificates are available after students satisfy
        the applicable course completion and final examination
        requirements.
      </p>
      <p>
        Projects are not compulsory for certificate eligibility
        unless a specific course explicitly states otherwise.
      </p>
      <p>
        Where a certificate fee applies, students must complete
        the required payment successfully before the certificate
        is unlocked.
      </p>
      <p>
        Certificates are generated using the registered student
        name and recorded course completion details.
      </p>

      <h2>8. Payments</h2>
      <p>
        Payments are processed through Razorpay or other
        officially supported payment services.
      </p>
      <ul>
        <li>Students must provide accurate payment information.</li>
        <li>Certificate access is granted only after successful payment verification.</li>
        <li>Submitting a payment request does not guarantee successful payment.</li>
        <li>Duplicate, pending or failed transactions may require verification.</li>
      </ul>

      <h2>9. Refund Policy</h2>
      <p>
        Refund requests are reviewed according to our applicable
        Refund Policy and relevant consumer protection laws.
        Students should contact support with their transaction
        reference when requesting payment assistance.
      </p>

      <h2>10. Acceptable Use</h2>
      <p>Students must not:</p>
      <ul>
        <li>Attempt to access another user's account.</li>
        <li>Misuse or disrupt platform services.</li>
        <li>Upload malicious files or harmful code.</li>
        <li>Attempt to manipulate examination results or payment records.</li>
        <li>Copy, distribute or commercially misuse protected learning materials without permission.</li>
        <li>Use the platform for unlawful activities.</li>
      </ul>

      <h2>11. Intellectual Property</h2>
      <p>
        The Skill Forge Learning name, logo, website design,
        course materials and original educational content
        are protected by applicable intellectual property laws.
      </p>
      <p>
        Students may use learning materials for personal
        educational purposes but may not reproduce,
        redistribute or sell protected content without
        authorization.
      </p>

      <h2>12. Service Availability</h2>
      <p>
        We aim to provide reliable access to our platform.
        However, temporary interruptions may occur due to
        maintenance, technical issues or circumstances
        beyond our control.
      </p>

      <h2>13. Account Suspension and Termination</h2>
      <p>
        We reserve the right to restrict or suspend accounts
        involved in fraud, unauthorized access, misuse or
        violations of these Terms, subject to applicable law.
      </p>

      <h2>14. Limitation of Liability</h2>
      <p>
        To the extent permitted by applicable law,
        Skill Forge Learning is not responsible for indirect
        losses arising from temporary service interruptions,
        unauthorized third-party activities or misuse of
        the platform.
      </p>

      <h2>15. Changes to Terms</h2>
      <p>
        We may revise these Terms when necessary.
        Updated Terms will be published on this page.
        Continued use of the platform after changes take
        effect is subject to the updated Terms, as permitted
        by applicable law.
      </p>

      <h2>16. Governing Law</h2>
      <p>
        These Terms are governed by the applicable laws of India.
        Any disputes will be handled by the competent courts
        having jurisdiction, subject to applicable law.
      </p>

      <h2>17. Contact Information</h2>
      <p>
        For questions about these Terms, contact:
      </p>
      <p>
        <strong>Skill Forge Learning</strong>
        <br />
        Email: skillforgelearning22@gmail.com
      </p>

      <p>
        Thank you for being part of Skill Forge Learning.
        <br />
        <strong>Learn. Practice. Build. Achieve.</strong>
      </p>

    </div>
  </Page>
);
