export default function BrandLogo({ className = "" }: { className?: string }) {
  return <img className={`brand-logo ${className}`.trim()} src="/skill-forge-learning-logo.png" alt="Skill Forge Learning" />;
}
