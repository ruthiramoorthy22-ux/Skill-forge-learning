/** Friendly student illustration drawn in SVG (no image files needed). */
export default function Illustration({ variant = "girl" }: { variant?: "girl" | "boy" }) {
  const hoodie = variant === "girl" ? "#f08a24" : "#0f766e";
  const hair = variant === "girl" ? "#3b2417" : "#1f2937";
  return (
    <svg className="illus" viewBox="0 0 220 240" role="img" aria-label="Student with a backpack and books">
      <ellipse cx="110" cy="226" rx="70" ry="9" fill="rgba(15,23,42,.12)" />
      <rect x="62" y="104" width="30" height="86" rx="14" fill="#1e3a8a" />
      <path d="M70 108h80l10 96H60z" fill={hoodie} />
      <path d="M92 108q18 24 36 0" fill="#fff" opacity=".35" />
      <rect x="64" y="200" width="36" height="22" rx="10" fill="#1f2937" /><rect x="118" y="200" width="36" height="22" rx="10" fill="#1f2937" />
      <rect x="82" y="150" width="68" height="50" rx="8" fill="#38bdf8" /><rect x="88" y="156" width="56" height="4" rx="2" fill="#fff" opacity=".7" />
      <circle cx="110" cy="70" r="34" fill="#f5c9a5" />
      <path d="M74 66q2-40 38-40t38 40q-10-18-38-18t-38 18z" fill={hair} />
      {variant === "girl" && <path d="M74 64q-12 40 2 70 6-30 6-56zM146 64q12 40-2 70-6-30-6-56z" fill={hair} />}
      <circle cx="98" cy="74" r="4" fill="#1f2937" /><circle cx="122" cy="74" r="4" fill="#1f2937" />
      <path d="M100 88q10 10 20 0" stroke="#b45309" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}
