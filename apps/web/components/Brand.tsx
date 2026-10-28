import Link from "next/link";

/** The plain "TY" monogram: a square with the two letters. `accent` colours the Y. */
export function Logo({ accent = "#B4452A", sw = 1.6 }: { accent?: string; sw?: number }) {
  return (
    <svg className="logo" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="1.5" y="1.5" width="25" height="25" rx="3" fill="none" stroke="currentColor" strokeWidth={sw} />
      <path d="M6.5 9H13M9.75 9V20" fill="none" stroke="currentColor" strokeWidth={sw + 0.6} strokeLinecap="square" />
      <path d="M14.5 9L18 14.2L21.5 9M18 14.2V20" fill="none" stroke={accent} strokeWidth={sw + 0.6} strokeLinecap="square" strokeLinejoin="miter" />
    </svg>
  );
}

export function Brand({ href = "/", accent }: { href?: string; accent?: string }) {
  return (
    <Link className="brand" href={href}>
      <Logo accent={accent} />
      <span>Travel Yantra</span>
    </Link>
  );
}
