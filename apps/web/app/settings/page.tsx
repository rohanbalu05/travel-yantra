"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell, LangPicker } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { NO_CONSENTS, deleteMyData, firebaseEnabled, saveConsents, signOut, useAccount, type Consents } from "@/lib/account";
import { useI18n } from "@/lib/i18n";
import "./settings.css";

// DPDP: each use of personal data has its own consent, off until the person turns it on.
const PURPOSES: { key: keyof Consents; title: string; what: string }[] = [
  { key: "plan_history", title: "Keep my trips", what: "Save the plans you make so they appear in My trips. Turning it off also deletes the trips saved so far." },
  { key: "location", title: "Use my location for emergencies", what: "Lets the guide use where you are, only when you tap Share my location, to find the nearest hospital, police or pharmacy." },
  { key: "analytics", title: "Help us measure Travel Yantra", what: "Sends anonymous timings (when you start, see a plan and pick a booking) with a random id. No name, email or trip details." },
];

export default function SettingsPage() {
  const account = useAccount();
  const { t } = useI18n();
  const [saving, setSaving] = useState<keyof Consents | null>(null);
  const [confirm, setConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState<string | null>(null);
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
      setDeleted(r.server === null ? "Deleted from this browser." : `Deleted from this browser and ${r.server} item${r.server === 1 ? "" : "s"} from our servers.`);
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
        <p className="page-sub">Your language, what you let us keep, and how to delete it all.</p>
      </div>

      {problem && <Problem {...problem} />}

      <section className="panel panel-pad st-sec" aria-labelledby="acc-h">
        <h2 className="h3" id="acc-h">Account</h2>
        {account.user ? (
          <div className="st-row">
            <div>
              <b>{account.user.name ?? account.user.email ?? "Signed in"}</b>
              <span className="hint">{account.user.demo ? "Demo account in this browser (Google sign-in is not set up here)." : account.user.email}</span>
            </div>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => void signOut()}>{t("Sign out")}</button>
          </div>
        ) : (
          <div className="st-row">
            <span className="hint">Not signed in. Plans still work; signing in keeps them across devices{firebaseEnabled ? "" : " once Google sign-in is set up"}.</span>
            <Link className="btn btn-primary btn-sm" href="/signin/">{t("Sign in")}</Link>
          </div>
        )}
      </section>

      <section className="panel panel-pad st-sec" aria-labelledby="lang-h">
        <h2 className="h3" id="lang-h">{t("Language")}</h2>
        <div className="st-row"><span className="hint">The app, your plans, the guide and Katha.</span><LangPicker /></div>
      </section>

      <section className="panel panel-pad st-sec" aria-labelledby="con-h">
        <h2 className="h3" id="con-h">What you allow</h2>
        <p className="hint" style={{ margin: 0 }}>
          Each is off until you turn it on, and you can turn it off at any time.{account.consents_updated_at ? ` Last changed ${new Date(account.consents_updated_at).toLocaleString("en-IN")}.` : ""}
        </p>
        {PURPOSES.map((p) => (
          <div className="st-consent" key={p.key}>
            <div>
              <b id={`c-${p.key}`}>{p.title}</b>
              <span className="hint">{p.what}</span>
            </div>
            <button type="button" role="switch" aria-checked={!!consents[p.key]} aria-labelledby={`c-${p.key}`} className={consents[p.key] ? "switch on" : "switch"} disabled={saving === p.key} onClick={() => void toggle(p.key)}>
              <span>{consents[p.key] ? "On" : "Off"}</span>
            </button>
          </div>
        ))}
      </section>

      <section className="panel panel-pad st-sec st-danger" aria-labelledby="del-h">
        <h2 className="h3" id="del-h">{t("Delete my data")}</h2>
        <p style={{ margin: 0 }}>Deletes your saved trips, your choices on this page and your account data. Shared plan links stop working. This cannot be undone.</p>
        {deleted ? (
          <p className="st-done" role="status">{deleted}</p>
        ) : (
          <form className="st-row" onSubmit={(e) => { e.preventDefault(); if (confirm === "DELETE") void remove(); }}>
            <label className="field" style={{ flex: "1 1 220px" }}>
              <span className="label">Type DELETE to confirm</span>
              <input className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
            </label>
            <button type="submit" className="btn btn-danger" disabled={confirm !== "DELETE" || deleting}>{deleting ? "Deleting…" : t("Delete my data")}</button>
          </form>
        )}
      </section>
    </AppShell>
  );
}
