// The PlantForge.ai mark. Two files, not one recoloured file: on light the
// mark is violet line art, on dark it is brushed steel, and neither is a
// filter applied to the other.
//
// The swap is CSS, not JS - both <img> are rendered and `dark:` toggles which
// is visible. That keeps the logo correct on first paint (a JS theme check
// flashes the wrong mark for a frame) and needs no theme context here.
//
// Sources are the trimmed square variants. The originals are framed very
// differently (LIGHT 432x457, DARK 677x369 with the mark floating small in the
// middle), so dropping the raw files into the same box renders the dark one
// noticeably smaller. logo-light/logo-dark are cropped to their ink and
// re-centred on matching square canvases, so any size prop holds for both.

import darkMark from "../assets/logo-dark.png";
import lightMark from "../assets/logo-light.png";

export default function Logo({ size = 32, className = "" }) {
  const common = {
    width: size,
    height: size,
    alt: "PlantForge.ai",
    style: { width: size, height: size, objectFit: "contain" },
  };
  return (
    <>
      <img {...common} src={lightMark} className={`block dark:hidden ${className}`} />
      <img {...common} src={darkMark} className={`hidden dark:block ${className}`} />
    </>
  );
}

/** The mark plus the wordmark, as used in the sidebar and on auth pages. */
export function Wordmark({ size = 32, className = "" }) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <Logo size={size} />
      <span
        className="font-bold tracking-tight"
        style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
      >
        PlantForge<span style={{ color: "var(--brand)" }}>.ai</span>
      </span>
    </span>
  );
}
