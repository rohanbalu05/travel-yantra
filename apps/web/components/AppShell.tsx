"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { Brand } from "@/components/Brand";
import { syncMe, useAccount, useSignInOffered } from "@/lib/account";
import type { Lang } from "@/lib/contracts";
import { LANGS, useI18n } from "@/lib/i18n";
import { NAV } from "@/lib/screens";

const globe = (
  <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18Z" />
  </svg>
);

/** "Arjun Rao (sample)" → "AR" */
const initials = (name: string) =>
  name.replace(/\(.*\)/g, "").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";

/** The six-language switch; each language is named in its own script. */
export function LangPicker() {
  const { lang, setLang, t } = useI18n();
  return (
    <label className="lang-pick">
      {globe}
      <span className="sr">{t("Choose a language")}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
        {LANGS.map((l) => (
          <option key={l.code} value={l.code} lang={l.code}>{l.native}</option>
        ))}
      </select>
    </label>
  );
}

/** The signed-in shell: app bar, main area, footer. */
let meAsked = false;

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname() ?? "";
  const { t } = useI18n();
  const user = useAccount()?.user;
  const offered = useSignInOffered();
  // Signed in with Google: ask /me once per page load, so the name and consents are the account's.
  const signedIn = !!user && !user.demo;
  useEffect(() => {
    if (signedIn && !meAsked) {
      meAsked = true;
      syncMe().catch(() => {});
    }
  }, [signedIn]);
  const on = (p: string) => path === p || (p !== "/home/" && path.startsWith(p.slice(0, -1)));
  return (
    <div className="app">
      <header className="appbar">
        <Brand href="/home/" />
        <nav className="appnav" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.path} href={n.path} className={on(n.path) ? "on" : undefined}>
              {t(n.label)}
            </Link>
          ))}
        </nav>
        <div className="appbar-end">
          <LangPicker />
          {user ? (
            <Link className="avatar" href="/settings/" aria-label={`${t("Settings")}: ${user.name ?? user.email ?? ""}`}>
              {initials(user.name ?? user.email ?? "?")}
            </Link>
          ) : (
            offered && <Link className="btn btn-quiet btn-sm" href="/signin/">{t("Sign in")}</Link>
          )}
        </div>
      </header>
      <main className="app-main">
        <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 44 }}>
          {children}
        </div>
      </main>
      <footer className="app-foot">
        <div className="wrap">
          <span>{t("Fares and timings are estimates. Check them with the seller before you pay.")}</span>
          <span>
            <Link href="/legal/">{t("Terms and privacy")}</Link>
            {" · "}
            <Link href="/privacy/">{t("Privacy policy")}</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
