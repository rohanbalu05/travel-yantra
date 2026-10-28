"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/Brand";
import { AuthProblem, finishRedirectSignIn, firebaseEnabled, resetPassword, signIn, signInWithEmail } from "@/lib/account";
import type { Lang } from "@/lib/contracts";
import "./signin.css";

// Google, or email and password (both Firebase). No phone number or SMS code (SMS costs money).
type Words = {
  name: string;
  cls: string;
  title: string;
  sub: string;
  google: string;
  or: string;
  email: string;
  password: string;
  signIn: string;
  create: string;
  toCreate: string;
  toSignIn: string;
  forgot: string;
};

const T = {
  en: { name: "English", cls: "", title: "Sign in to plan your trip", sub: "Your plans, bookings and Katha stay saved on your phone and your computer.", google: "Continue with Google", or: "or with email", email: "Email", password: "Password", signIn: "Sign in", create: "Create account", toCreate: "New here? Create an account", toSignIn: "Have an account? Sign in", forgot: "Forgot password?" },
  kn: { name: "ಕನ್ನಡ", cls: "kn", title: "ನಿಮ್ಮ ಪ್ರವಾಸ ಯೋಜಿಸಲು ಸೈನ್ ಇನ್ ಮಾಡಿ", sub: "ನಿಮ್ಮ ಯೋಜನೆಗಳು, ಬುಕಿಂಗ್‌ಗಳು ಮತ್ತು ಕಥೆಗಳು ನಿಮ್ಮ ಫೋನ್ ಮತ್ತು ಕಂಪ್ಯೂಟರ್‌ನಲ್ಲಿ ಉಳಿಯುತ್ತವೆ.", google: "Google ಮೂಲಕ ಮುಂದುವರಿಯಿರಿ", or: "ಅಥವಾ ಇಮೇಲ್ ಮೂಲಕ", email: "ಇಮೇಲ್", password: "ಪಾಸ್‌ವರ್ಡ್", signIn: "ಸೈನ್ ಇನ್", create: "ಖಾತೆ ರಚಿಸಿ", toCreate: "ಹೊಸಬರೇ? ಖಾತೆ ರಚಿಸಿ", toSignIn: "ಖಾತೆ ಇದೆಯೇ? ಸೈನ್ ಇನ್ ಮಾಡಿ", forgot: "ಪಾಸ್‌ವರ್ಡ್ ಮರೆತಿರಾ?" },
  hi: { name: "हिन्दी", cls: "hi", title: "अपनी यात्रा प्लान करने के लिए साइन इन करें", sub: "आपके प्लान, बुकिंग और कथाएँ आपके फ़ोन और कंप्यूटर पर सहेजी रहती हैं।", google: "Google से जारी रखें", or: "या ईमेल से", email: "ईमेल", password: "पासवर्ड", signIn: "साइन इन करें", create: "खाता बनाएँ", toCreate: "नए हैं? खाता बनाएँ", toSignIn: "खाता है? साइन इन करें", forgot: "पासवर्ड भूल गए?" },
  ta: { name: "தமிழ்", cls: "ta", title: "உங்கள் பயணத்தைத் திட்டமிட உள்நுழையுங்கள்", sub: "உங்கள் திட்டங்கள், முன்பதிவுகள், கதைகள் அனைத்தும் உங்கள் ஃபோனிலும் கணினியிலும் சேமிக்கப்படும்.", google: "Google மூலம் தொடரவும்", or: "அல்லது மின்னஞ்சல் மூலம்", email: "மின்னஞ்சல்", password: "கடவுச்சொல்", signIn: "உள்நுழை", create: "கணக்கை உருவாக்கு", toCreate: "புதியவரா? கணக்கை உருவாக்குங்கள்", toSignIn: "கணக்கு உள்ளதா? உள்நுழையுங்கள்", forgot: "கடவுச்சொல் மறந்ததா?" },
  te: { name: "తెలుగు", cls: "te", title: "మీ ప్రయాణాన్ని ప్లాన్ చేయడానికి సైన్ ఇన్ చేయండి", sub: "మీ ప్లాన్‌లు, బుకింగ్‌లు, కథలు మీ ఫోన్‌లో, కంప్యూటర్‌లో సేవ్ అయి ఉంటాయి.", google: "Googleతో కొనసాగించండి", or: "లేదా ఈమెయిల్‌తో", email: "ఈమెయిల్", password: "పాస్‌వర్డ్", signIn: "సైన్ ఇన్", create: "ఖాతా సృష్టించండి", toCreate: "కొత్తవారా? ఖాతా సృష్టించండి", toSignIn: "ఖాతా ఉందా? సైన్ ఇన్ చేయండి", forgot: "పాస్‌వర్డ్ మర్చిపోయారా?" },
  bn: { name: "বাংলা", cls: "bn", title: "আপনার ভ্রমণের পরিকল্পনা করতে সাইন ইন করুন", sub: "আপনার প্ল্যান, বুকিং আর কথা আপনার ফোন ও কম্পিউটারে সেভ থাকবে।", google: "Google দিয়ে চালিয়ে যান", or: "অথবা ইমেল দিয়ে", email: "ইমেল", password: "পাসওয়ার্ড", signIn: "সাইন ইন", create: "অ্যাকাউন্ট তৈরি করুন", toCreate: "নতুন? অ্যাকাউন্ট তৈরি করুন", toSignIn: "অ্যাকাউন্ট আছে? সাইন ইন করুন", forgot: "পাসওয়ার্ড ভুলে গেছেন?" },
} as const satisfies Record<Lang, Words>;

/** Plain words for Firebase's error codes. */
function authMessage(code: string): string {
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
    case "auth/invalid-login-credentials":
      return "That email and password don't match an account. Check them, or reset your password.";
    case "auth/email-already-in-use":
      return "An account with this email already exists. Sign in instead, or reset your password.";
    case "auth/weak-password":
      return "Use a password of at least 6 characters.";
    case "auth/invalid-email":
    case "auth/missing-email":
      return "Enter a valid email address.";
    case "auth/missing-password":
      return "Enter your password.";
    case "auth/too-many-requests":
      return "Too many tries. Wait a few minutes, or reset your password.";
    case "auth/network-request-failed":
      return "No connection. Check your internet and try again.";
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "The Google window was closed before sign-in finished. Try again.";
    case "auth/popup-blocked":
      return "Your browser blocked the Google window. Allow popups for this site, or sign in with email.";
    case "auth/operation-not-allowed":
      return "This way of signing in isn't switched on yet. Use another, or keep planning without an account.";
    default:
      return "Sign-in did not finish. Try again, or keep planning without an account.";
  }
}

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const router = useRouter();
  const t = T[lang];

  // Back from Google's page on a phone: finish the sign-in this load started.
  useEffect(() => {
    let live = true;
    finishRedirectSignIn()
      .then((u) => {
        if (live && u) router.push("/home/");
      })
      .catch((e) => live && setError(authMessage(AuthProblem.from(e).code)));
    return () => {
      live = false;
    };
  }, [router]);

  const run = async (call: () => Promise<unknown>) => {
    setTried(true);
    setError(null);
    setNotice(null);
    if (!agree) return;
    setBusy(true);
    try {
      const u = await call();
      if (u) router.push("/home/");
    } catch (e) {
      setError(authMessage(AuthProblem.from(e).code));
    } finally {
      setBusy(false);
    }
  };

  const google = () => run(() => signIn());
  const byEmail = () => run(() => signInWithEmail(email, password, creating));

  const forgot = async () => {
    setError(null);
    setNotice(null);
    if (!email.trim()) return setError(authMessage("auth/missing-email"));
    setBusy(true);
    try {
      await resetPassword(email);
      setNotice(`If ${email.trim()} has an account, a reset link is on its way. Check your inbox and spam folder.`);
    } catch (e) {
      setError(authMessage(AuthProblem.from(e).code));
    } finally {
      setBusy(false);
    }
  };

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
                I agree to the <Link href="/legal/">Terms of Service</Link> and the <Link href="/legal/">Privacy Policy</Link>, and to Travel Yantra using my trip details to plan my trips. Required.
              </span>
            </label>
            <label className="check">
              <input type="checkbox" checked={wa} onChange={() => setWa(!wa)} />
              <span>Send me trip updates on WhatsApp. Optional, and I can stop them any time.</span>
            </label>
          </div>

          <button type="button" className="btn btn-dark btn-lg btn-block" disabled={busy} onClick={() => void google()}>
            <span className={t.cls}>{t.google}</span>
          </button>

          {firebaseEnabled && (
            <>
              <div className={`si-or ${t.cls}`}>{t.or}</div>
              <form
                className="si-email"
                onSubmit={(e) => {
                  e.preventDefault();
                  void byEmail();
                }}
              >
                <label className="field">
                  <span className={`label ${t.cls}`}>{t.email}</span>
                  <input className="input" type="email" autoComplete="email" inputMode="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </label>
                <label className="field">
                  <span className={`label ${t.cls}`}>{t.password}</span>
                  <input className="input" type="password" autoComplete={creating ? "new-password" : "current-password"} minLength={6} required value={password} onChange={(e) => setPassword(e.target.value)} />
                </label>
                <button type="submit" className="btn btn-lg btn-block" disabled={busy}>
                  <span className={t.cls}>{creating ? t.create : t.signIn}</span>
                </button>
                <div className="si-links">
                  <button type="button" className="si-link" onClick={() => setCreating(!creating)}>
                    <span className={t.cls}>{creating ? t.toSignIn : t.toCreate}</span>
                  </button>
                  {!creating && (
                    <button type="button" className="si-link" disabled={busy} onClick={() => void forgot()}>
                      <span className={t.cls}>{t.forgot}</span>
                    </button>
                  )}
                </div>
              </form>
            </>
          )}

          {tried && !agree && (
            <p className="si-err" role="alert">
              Tick the first box to agree to the Terms and the Privacy Policy, then continue.
            </p>
          )}
          {error && (
            <p className="si-err" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="si-ok" role="status">
              {notice}
            </p>
          )}

          <p className="si-small">
            Just looking? <Link href="/katha/">Listen to a Katha</Link> first, no account needed.
          </p>
        </div>
      </main>
    </div>
  );
}
