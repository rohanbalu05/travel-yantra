"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Brand } from "@/components/Brand";
import { NAV } from "@/lib/screens";

const globe = (
  <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18Z" />
  </svg>
);

/** The signed-in shell: app bar, main area, footer. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname() ?? "";
  const on = (p: string) => path === p || (p !== "/home/" && path.startsWith(p.slice(0, -1)));
  return (
    <div className="app">
      <header className="appbar">
        <Brand href="/home/" />
        <nav className="appnav" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.path} href={n.path} className={on(n.path) ? "on" : undefined}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="appbar-end">
          <Link className="btn btn-quiet btn-sm" href="/settings/">
            {globe}English
          </Link>
          <Link className="avatar" href="/settings/" aria-label="Account and settings">
            AR
          </Link>
        </div>
      </header>
      <main className="app-main">
        <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 44 }}>
          {children}
        </div>
      </main>
      <footer className="app-foot">
        <div className="wrap">
          <span>Travel Yantra prototype. Trips, fares and timings shown are sample data.</span>
          <span>
            <Link href="/legal/">Terms and privacy</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
