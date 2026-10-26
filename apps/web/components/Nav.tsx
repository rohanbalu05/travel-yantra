"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SCREENS, TABS } from "@/lib/screens";

export function TopBar() {
  return (
    <header className="topbar">
      <Link href="/" className="brand">
        Travel<span>Yantra</span>
      </Link>
      <details className="menu">
        <summary aria-label="All screens">Menu</summary>
        <nav className="menu-panel" aria-label="All screens">
          <ul>
            {SCREENS.map((s) => (
              <li key={s.slug}>
                <Link href={s.path}>{s.title}</Link>
              </li>
            ))}
          </ul>
        </nav>
      </details>
    </header>
  );
}

export function TabBar() {
  const pathname = usePathname() ?? "";
  const section = (p: string) => "/" + (p.split("/")[1] ?? "");
  return (
    <nav className="tabs" aria-label="Main">
      {TABS.map((t) => (
        <Link
          key={t.path}
          href={t.path}
          aria-current={section(pathname) === section(t.path) ? "page" : undefined}
        >
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
