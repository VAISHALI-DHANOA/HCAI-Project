import "./Brand.css";
export function Brand({ className = "" }: { className?: string }) {
  return <div className={`entry-screen__brand ${className}`} aria-label="The Arena, a multi-agent playground">
    <div className="brand-mark" aria-hidden="true">A</div>
    <div className="entry-brand-copy">
      <span className="entry-brand-name">THE ARENA</span>
      <span className="entry-brand-tagline">A multi-agent playground</span>
    </div>
  </div>;
}
