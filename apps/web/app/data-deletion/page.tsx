import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import "../settings/settings.css";

export const metadata = { title: "Delete your data · Travel Yantra" };

const CONTACT = "rohan@aizyantra.com";

export default function DataDeletionPage() {
  return (
    <AppShell>
      <article className="legal-doc">
        <h1 className="page-title">Delete your data</h1>
        <p className="hint">You can delete everything Travel Yantra keeps about you, at any time, at no cost.</p>

        <h2 className="h3">On the web</h2>
        <ol>
          <li>Open <Link href="/settings/">Settings</Link>.</li>
          <li>Under <i>Delete my data</i>, type DELETE and press the button.</li>
        </ol>
        <p>This deletes, on our servers, the trips saved under your browser&apos;s anonymous id (their share links stop working), your consent choices and your ratings; and, in your browser, your account, saved trips, ratings and the plan in progress. Your browser then starts with a new anonymous id, so nothing links back.</p>

        <h2 className="h3">On WhatsApp</h2>
        <p>Send <b>delete my data</b> to the Travel Yantra bot. It deletes the plan and language it holds for your number.</p>

        <h2 className="h3">By email</h2>
        <p>Write to <a href={`mailto:${CONTACT}`}>{CONTACT}</a> with the subject &quot;Delete my data&quot;. Tell us the WhatsApp number you used, or the share link of a plan, so we can find it. We never ask for an OTP or password.</p>

        <h2 className="h3">What stays</h2>
        <p>Plans that were never linked to you (made without <i>Keep my trips</i>) cannot be traced to you; they keep working only through their share link. Anonymous study timings carry no id we can match to you.</p>

        <p><Link href="/privacy/">Read the privacy policy</Link></p>
      </article>
    </AppShell>
  );
}
