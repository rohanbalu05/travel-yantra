import Link from "next/link";

export function Logo({ accent = "#B4452A", sw = 1.6 }: { accent?: string; sw?: number }) {
  return (
    <svg className="logo" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="1.5" y="1.5" width="25" height="25" fill="none" stroke="currentColor" strokeWidth={sw} />
      <circle cx="14" cy="14" r="9" fill="none" stroke="currentColor" strokeWidth={sw} />
      <path d="M14 6.5L21 18.5H7Z" fill="none" stroke="currentColor" strokeWidth={sw} />
      <path d="M14 21.5L7 9.5H21Z" fill="none" stroke={accent} strokeWidth={sw} />
      <circle cx="14" cy="14" r="1.8" fill={accent} />
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
