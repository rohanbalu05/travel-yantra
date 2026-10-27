"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell, LangPicker } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { NO_CONSENTS, deleteMyData, firebaseEnabled, saveConsents, signOut, syncMe, useAccount, type Consents } from "@/lib/account";
import { useI18n } from "@/lib/i18n";
import "./settings.css";

// DPDP: each use of personal data has its own consent, off until the person turns it on.
// title and what are dictionary keys, translated where they are shown.
const PURPOSES: { key: keyof Consents; title: string; what: string }[] = [
  { key: "plan_history", title: "Keep my trips", what: "Save the plans you make so they appear in My trips. Turning it off also deletes the trips saved so far." },
  { key: "location", title: "Use my location for emergencies", what: "Lets the guide use where you are, only when you tap Share my location, to find the nearest hospital, police or pharmacy." },
  { key: "analytics", title: "Help us measure Travel Yantra", what: "Sends anonymous timings (when you start, see a plan and pick a booking) with a random id. No name, email or trip details." },
];

export default function SettingsPage() {
  const account = useAccount();
  // The server (TY1's GET /me) is the truth for consents once it has them; no-op without an API.
  useEffect(() => {
    void syncMe().catch(() => {});
  }, []);
  const { t } = useI18n();
  const [saving, setSaving] = useState<keyof Consents | null>(null);
  const [confirm, setConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  // How many server items were deleted (null: only this browser), or not deleted yet.
  const [deleted, setDeleted] = useState<{ server: number | null } | null>(null);
  const [problem, setProblem] = useState<{ message: string; retryable: boolean } | null>(null);

  if (account === undefined) return <AppShell>{null}</AppShell>;
  const consents = { ...NO_CONSENTS, ...account.consents };

  const toggle = async (key: keyof Consents) => {
    setSaving(key);
    setProblem(null);
    try {
      await saveConsents({ ...consents, [key]: !consents[key] });
    } catch (e) {
      setProblem(problemOf(e));
    } finally {
      setSaving(null);
    }
  };

  const remove = async () => {
    setDeleting(true);
    setProblem(null);
    try {
      const r = await deleteMyData();
      setDeleted({ server: r.server });
      setConfirm("");
    } catch (e) {
      setProblem(problemOf(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AppShell>
      <div className="st-head">
        <h1 className="page-title">{t("Settings")}</h1>
        <p className="page-sub">{t("Your language, what you let us keep, and how to delete it all.")}</p>
      </div>

      {problem && <Problem {...problem} />}

      <section className="panel panel-pad st-sec" aria-labelledby="acc-h">
        <h2 className="h3" id="acc-h">{t("Account")}</h2>
        {account.user ? (
          <div className="st-row">
            <div>
              <b>{account.user.name ?? account.user.email ?? t("Signed in")}</b>
              <span className="hint">{account.user.demo ? t("Demo account in this browser (Google sign-in is not set up here).") : account.user.email}</span>
            </div>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => void signOut()}>{t("Sign out")}</button>
          </div>
        ) : (
          <div className="st-row">
            <span className="hint">{firebaseEnabled ? t("Not signed in. Plans still work; signing in keeps them across devices.") : t("Not signed in. Plans still work; signing in keeps them across devices once Google sign-in is set up.")}</span>
            <Link className="btn btn-primary btn-sm" href="/signin/">{t("Sign in")}</Link>
          </div>
        )}
      </section>

      <section className="panel panel-pad st-sec" aria-labelledby="lang-h">
        <h2 className="h3" id="lang-h">{t("Language")}</h2>
        <div className="st-row"><span className="hint">{t("The app, your plans, the guide and Katha.")}</span><LangPicker /></div>
      </section>

      <section className="panel panel-pad st-sec" aria-labelledby="con-h">
        <h2 className="h3" id="con-h">{t("What you allow")}</h2>
        <p className="hint" style={{ margin: 0 }}>
          {t("Each is off until you turn it on, and you can turn it off at any time.")}{account.consents_updated_at ? ` ${t("Last changed {when}.", { when: new Date(account.consents_updated_at).toLocaleString("en-IN") })}` : ""}
        </p>
        {PURPOSES.map((p) => (
          <div className="st-consent" key={p.key}>
            <div>
              <b id={`c-${p.key}`}>{t(p.title)}</b>
              <span className="hint">{t(p.what)}</span>
            </div>
            <button type="button" role="switch" aria-checked={!!consents[p.key]} aria-labelledby={`c-${p.key}`} className={consents[p.key] ? "switch on" : "switch"} disabled={saving === p.key} onClick={() => void toggle(p.key)}>
              <span>{consents[p.key] ? t("On") : t("Off")}</span>
            </button>
          </div>
        ))}
      </section>

      <section className="panel panel-pad st-sec st-danger" aria-labelledby="del-h">
        <h2 className="h3" id="del-h">{t("Delete my data")}</h2>
        <p style={{ margin: 0 }}>{t("Deletes your saved trips, your choices on this page and your account data. Shared plan links stop working. This cannot be undone.")}</p>
        {deleted ? (
          <p className="st-done" role="status">
            {deleted.server === null
              ? t("Deleted from this browser.")
              : deleted.server === 1
                ? t("Deleted from this browser and {n} item from our servers.", { n: deleted.server })
                : t("Deleted from this browser and {n} items from our servers.", { n: deleted.server })}
          </p>
        ) : (
          <form className="st-row" onSubmit={(e) => { e.preventDefault(); if (confirm === "DELETE") void remove(); }}>
            <label className="field" style={{ flex: "1 1 220px" }}>
              <span className="label">{t("Type DELETE to confirm")}</span>
              <input className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
            </label>
            <button type="submit" className="btn btn-danger" disabled={confirm !== "DELETE" || deleting}>{deleting ? t("Deleting…") : t("Delete my data")}</button>
          </form>
        )}
      </section>
    </AppShell>
  );
}
