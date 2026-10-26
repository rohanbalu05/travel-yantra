"use client";

import Link from "next/link";
import { useState } from "react";
import { Brand } from "@/components/Brand";
import "./signin.css";

// Google only: no phone number or SMS code (SMS costs money).
const T = {
  en: { name: "English", cls: "", title: "Sign in to plan your trip", sub: "Your plans, bookings and Katha stay saved on your phone and your computer.", google: "Continue with Google" },
  kn: { name: "ಕನ್ನಡ", cls: "kn", title: "ನಿಮ್ಮ ಪ್ರವಾಸ ಯೋಜಿಸಲು ಸೈನ್ ಇನ್ ಮಾಡಿ", sub: "ನಿಮ್ಮ ಯೋಜನೆಗಳು, ಬುಕಿಂಗ್‌ಗಳು ಮತ್ತು ಕಥೆಗಳು ನಿಮ್ಮ ಫೋನ್ ಮತ್ತು ಕಂಪ್ಯೂಟರ್‌ನಲ್ಲಿ ಉಳಿಯುತ್ತವೆ.", google: "Google ಮೂಲಕ ಮುಂದುವರಿಯಿರಿ" },
  hi: { name: "हिन्दी", cls: "hi", title: "अपनी यात्रा प्लान करने के लिए साइन इन करें", sub: "आपके प्लान, बुकिंग और कथाएँ आपके फ़ोन और कंप्यूटर पर सहेजी रहती हैं।", google: "Google से जारी रखें" },
  ta: { name: "தமிழ்", cls: "ta", title: "உங்கள் பயணத்தைத் திட்டமிட உள்நுழையுங்கள்", sub: "உங்கள் திட்டங்கள், முன்பதிவுகள், கதைகள் அனைத்தும் உங்கள் ஃபோனிலும் கணினியிலும் சேமிக்கப்படும்.", google: "Google மூலம் தொடரவும்" },
  te: { name: "తెలుగు", cls: "te", title: "మీ ప్రయాణాన్ని ప్లాన్ చేయడానికి సైన్ ఇన్ చేయండి", sub: "మీ ప్లాన్‌లు, బుకింగ్‌లు, కథలు మీ ఫోన్‌లో, కంప్యూటర్‌లో సేవ్ అయి ఉంటాయి.", google: "Googleతో కొనసాగించండి" },
  bn: { name: "বাংলা", cls: "bn", title: "আপনার ভ্রমণের পরিকল্পনা করতে সাইন ইন করুন", sub: "আপনার প্ল্যান, বুকিং আর কথা আপনার ফোন ও কম্পিউটারে সেভ থাকবে।", google: "Google দিয়ে চালিয়ে যান" },
} as const;
type Lang = keyof typeof T;

const words: [string, string, string][] = [
  ["kn", "ಪ್ರಯಾಣ", "Kannada"],
  ["hi", "यात्रा", "Hindi"],
  ["ta", "பயணம்", "Tamil"],
  ["te", "ప్రయాణం", "Telugu"],
  ["bn", "যাত্রা", "Bengali"],
  ["", "Journey", "English"],
];

const points: [string, string][] = [
  ["M5 12.5l4.5 4.5L19 7.5", "Plans checked stop by stop for hours, travel time, meals and budget."],
  ["M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5ZM4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5", "A Katha for every place, with history and legend told apart."],
  ["M4 7h16v12H4zM8 7V4h8v3M4 12h16", "Bookings handed to the official sellers, then watched for you."],
];

export default function SignInPage() {
  const [lang, setLang] = useState<Lang>("en");
  const [agree, setAgree] = useState(false);
  const [wa, setWa] = useState(false);
  const [tried, setTried] = useState(false);
  const t = T[lang];
  const google = <span className={t.cls}>{t.google}</span>;

  return (
    <div className="si">
      <aside className="si-art">
        <svg className="si-yantra" viewBox="0 0 680 680" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <rect x="20" y="20" width="640" height="640" />
          <rect x="60" y="60" width="560" height="560" />
          <circle cx="340" cy="340" r="250" />
          <circle cx="340" cy="340" r="210" />
          <path d="M340 130L522 445H158Z" />
          <path d="M340 550L158 235H522Z" />
          <path d="M340 190L470 415H210Z" />
          <path d="M340 490L210 265H470Z" />
          <circle cx="340" cy="340" r="14" />
        </svg>
        <Brand accent="#E07A52" />
        <div className="si-words" aria-label="The word for journey in six languages">
          {words.map(([cls, w, name]) => (
            <div className="si-w" key={name}>
              <span className={cls}>{w}</span>
              <small>{name}</small>
            </div>
          ))}
        </div>
        <ul className="si-list">
          {points.map(([d, text]) => (
            <li key={text}>
              <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                <path d={d} />
              </svg>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <p className="si-foot">A final-year project at BMS Institute of Technology and Management, Bengaluru.</p>
      </aside>

      <main className="si-main">
        <div className="si-top">
          <Link className="btn btn-quiet btn-sm" href="/">
            Back to the website
          </Link>
        </div>

        <div className="si-form">
          <div className="si-langhead">
            <span className="label">Choose your language</span>
            <div className="langs" role="group" aria-label="Language">
              {(Object.keys(T) as Lang[]).map((k) => (
                <button key={k} type="button" className={`lang ${T[k].cls}${k === lang ? " on" : ""}`} onClick={() => setLang(k)}>
                  {T[k].name}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h1 className={`si-title ${t.cls}`}>{t.title}</h1>
            <p className={`page-sub ${t.cls}`}>{t.sub}</p>
          </div>

          <div className="si-consent">
            <label className="check">
              <input type="checkbox" checked={agree} onChange={() => setAgree(!agree)} />
              <span>
                I agree to the <Link href="/legal/">Terms of Service</Link> and the <Link href="/legal/">Privacy Policy</Link>, and to Travel Yantra using my trip details to plan my trips.
              </span>
            </label>
            <label className="check">
              <input type="checkbox" checked={wa} onChange={() => setWa(!wa)} />
              <span>Send me trip updates on WhatsApp. Optional, and I can stop them any time.</span>
            </label>
          </div>

          {agree ? (
            <Link className="btn btn-dark btn-lg btn-block" href="/home/">
              {google}
            </Link>
          ) : (
            <button type="button" className="btn btn-dark btn-lg btn-block" onClick={() => setTried(true)}>
              {google}
            </button>
          )}

          {tried && !agree && (
            <p className="si-err" role="alert">
              Tick the first box to agree to the Terms and the Privacy Policy, then continue.
            </p>
          )}

          <p className="si-small">
            New here? Signing in creates your account. Just looking? <Link href="/katha/city/">Listen to a Katha</Link> first, no account needed.
          </p>
        </div>
      </main>
    </div>
  );
}
