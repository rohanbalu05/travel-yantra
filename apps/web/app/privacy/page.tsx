import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import "../settings/settings.css";

export const metadata = { title: "Privacy policy · Travel Yantra" };

const CONTACT = "rohan@aizyantra.com";

// Plain and short on purpose. Keep it true to what the code does; update it when that changes.
export default function PrivacyPage() {
  return (
    <AppShell>
      <article className="legal-doc">
        <h1 className="page-title">Privacy policy</h1>
        <p className="hint">Last updated 27 October 2026. Travel Yantra is a prototype; the trips, fares and people shown in it are sample data.</p>

        <h2 className="h3">Who we are</h2>
        <p>Travel Yantra plans trips in India, tells the story of places and answers travel questions, on the web and on WhatsApp. Contact: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.</p>

        <h2 className="h3">What we keep, and why</h2>
        <ul>
          <li><b>Your plans.</b> When you plan a trip we keep the plan so its share link works. It is not linked to you unless you turn on <i>Keep my trips</i>, which links new plans to your browser&apos;s anonymous id so they appear in My trips.</li>
          <li><b>An anonymous id.</b> Your browser makes a random id the first time it talks to us. We use it to keep your consent choices, your saved trips and your ratings together. It is not your name, email or phone number.</li>
          <li><b>Your consent choices</b> and when you last changed them.</li>
          <li><b>Ratings</b> you give a plan (1 to 5) and any note you add.</li>
          <li><b>Timings</b>, only if you turn on <i>Help us measure</i> or join a study: when you start planning, see a plan and choose a booking, with a random id for that session. Nothing you type is included.</li>
        </ul>
        <p>Your language choice and a copy of your current plan stay in your browser.</p>

        <h2 className="h3">What we do not collect</h2>
        <p>We do not ask for your name, phone number or payment details on the web, and we never take card numbers, UPI ids or OTPs. Bookings happen on the seller&apos;s own site, under their policy.</p>

        <h2 className="h3">Consent (DPDP Act, 2023)</h2>
        <p>Each use above that needs consent has its own switch in <Link href="/settings/">Settings</Link>, off until you turn it on: <i>Keep my trips</i>, <i>Use my location for emergencies</i> and <i>Help us measure</i>. Your location is read only when you tap <i>Share my location</i>, and only sent with that question to the guide. You can turn any of them off at any time; turning off <i>Keep my trips</i> also deletes the trips saved under it.</p>

        <h2 className="h3">WhatsApp</h2>
        <p>If you plan with our WhatsApp bot, it keeps only your current plan and your language, in memory, to continue the conversation. Messages pass through WhatsApp (Meta) under its own terms.</p>

        <h2 className="h3">Who processes it</h2>
        <p>We run on Google Cloud in India (Mumbai region). Your trip request and your questions are processed by Google&apos;s Gemini models on Vertex AI to write plans, stories and answers. Places come from Google Maps data and stories cite public sources such as Wikipedia and Wikivoyage.</p>

        <h2 className="h3">Deleting your data</h2>
        <p>See <Link href="/data-deletion/">how to delete your data</Link>. In short: Settings → Delete my data on the web, or send &quot;delete my data&quot; to the WhatsApp bot, or email us.</p>

        <h2 className="h3">Questions or complaints</h2>
        <p>Email <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.</p>
      </article>
    </AppShell>
  );
}
