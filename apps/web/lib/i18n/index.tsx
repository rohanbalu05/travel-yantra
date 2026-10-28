"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import type { Lang } from "@/lib/contracts";
import phrasebook from "@/lib/i18n/phrasebook.json";
import screensGuide from "@/lib/i18n/screens-guide.json";
import screensP8 from "@/lib/i18n/screens-p8.json";
import screensPlan from "@/lib/i18n/screens-plan.json";

export const LANGS: { code: Lang; native: string; english: string }[] = [
  { code: "en", native: "English", english: "English" },
  { code: "hi", native: "हिन्दी", english: "Hindi" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada" },
  { code: "ta", native: "தமிழ்", english: "Tamil" },
  { code: "te", native: "తెలుగు", english: "Telugu" },
  { code: "bn", native: "বাংলা", english: "Bengali" },
];

type Entry = Partial<Record<Lang, string>>;

// Web-only strings that are not in TY5's phrasebook (services/translate/app/phrasebook.tsv).
// UNREVIEWED: drafted in TY4; send to TY5 for the phrasebook review before the demo.
const EXTRA: Record<string, Entry> = {
  Home: { hi: "होम", kn: "ಮುಖಪುಟ", ta: "முகப்பு", te: "హోమ్", bn: "হোম" },
  "Plan a trip": { hi: "यात्रा की योजना बनाएं", kn: "ಪ್ರವಾಸ ಯೋಜಿಸಿ", ta: "பயணத்தைத் திட்டமிடுங்கள்", te: "యాత్ర ప్లాన్ చేయండి", bn: "ভ্রমণের পরিকল্পনা" },
  Katha: { hi: "कथा", kn: "ಕಥೆ", ta: "கதை", te: "కథ", bn: "কথা" },
  "My trips": { hi: "मेरी यात्राएं", kn: "ನನ್ನ ಪ್ರವಾಸಗಳು", ta: "என் பயணங்கள்", te: "నా యాత్రలు", bn: "আমার ভ্রমণ" },
  "Ask the guide": { hi: "गाइड से पूछें", kn: "ಮಾರ್ಗದರ್ಶಿಯನ್ನು ಕೇಳಿ", ta: "வழிகாட்டியிடம் கேளுங்கள்", te: "గైడ్‌ను అడగండి", bn: "গাইডকে জিজ্ঞাসা করুন" },
  "Tell us about the trip": { hi: "यात्रा के बारे में बताएं", kn: "ಪ್ರವಾಸದ ಬಗ್ಗೆ ತಿಳಿಸಿ", ta: "பயணத்தைப் பற்றி சொல்லுங்கள்", te: "యాత్ర గురించి చెప్పండి", bn: "ভ্রমণের কথা বলুন" },
  "Book this plan": { hi: "यह योजना बुक करें", kn: "ಈ ಯೋಜನೆಯನ್ನು ಬುಕ್ ಮಾಡಿ", ta: "இந்தத் திட்டத்தை முன்பதிவு செய்யுங்கள்", te: "ఈ ప్లాన్‌ను బుక్ చేయండి", bn: "এই পরিকল্পনা বুক করুন" },
  "Your plan is ready": { hi: "आपकी योजना तैयार है", kn: "ನಿಮ್ಮ ಯೋಜನೆ ಸಿದ್ಧವಾಗಿದೆ", ta: "உங்கள் திட்டம் தயார்", te: "మీ ప్లాన్ సిద్ధంగా ఉంది", bn: "আপনার পরিকল্পনা তৈরি" },
  "Sign in": { hi: "साइन इन करें", kn: "ಸೈನ್ ಇನ್ ಮಾಡಿ", ta: "உள்நுழையுங்கள்", te: "సైన్ ఇన్ చేయండి", bn: "সাইন ইন করুন" },
  "Sign out": { hi: "साइन आउट करें", kn: "ಸೈನ್ ಔಟ್ ಮಾಡಿ", ta: "வெளியேறு", te: "సైన్ అవుట్ చేయండి", bn: "সাইন আউট করুন" },
  "Delete my data": { hi: "मेरा डेटा हटाएं", kn: "ನನ್ನ ಡೇಟಾ ಅಳಿಸಿ", ta: "என் தரவை நீக்கு", te: "నా డేటాను తొలగించండి", bn: "আমার ডেটা মুছুন" },
  "Rate this plan": { hi: "इस योजना को रेट करें", kn: "ಈ ಯೋಜನೆಗೆ ರೇಟಿಂಗ್ ನೀಡಿ", ta: "இந்தத் திட்டத்தை மதிப்பிடுங்கள்", te: "ఈ ప్లాన్‌కు రేటింగ్ ఇవ్వండి", bn: "এই পরিকল্পনাকে রেটিং দিন" },
};

// Screen strings drafted in TY4 (P4), one file per group of screens. UNREVIEWED: Rohan's native-speaker
// teammates review them. Keys are the English text; "{name}" marks a value filled in at run time.
const DICT: Record<string, Entry> = {
  ...(screensPlan as Record<string, Entry>),
  ...(screensGuide as Record<string, Entry>),
  ...(screensP8 as Record<string, Entry>),
  ...(phrasebook as Record<string, Entry>),
  ...EXTRA,
};

export type Vars = Record<string, string | number>;

/** The text in `lang` (English when there is no translation yet), with {name} slots filled from vars. */
export function translate(text: string, lang: Lang, vars?: Vars): string {
  const s = lang === "en" ? text : (DICT[text]?.[lang] ?? text);
  return vars ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : s;
}

/** Every English key, for tests that check each has all five translations. */
export const DICTIONARY_KEYS = () => Object.keys(DICT);
export const dictionaryEntry = (en: string) => DICT[en];

const KEY = "ty.lang";
const CHANGED = "ty-lang";

const isLang = (x: unknown): x is Lang => LANGS.some((l) => l.code === x);

// The choice also lives here, so the switch works when storage is blocked (it then lasts until reload).
let chosen: Lang | null = null;

function readLang(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    return isLang(v) ? v : "en";
  } catch {
    return chosen ?? "en"; // storage blocked: the in-memory choice
  }
}

function subscribe(cb: () => void) {
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", cb);
  };
}

export function saveLang(lang: Lang) {
  chosen = lang;
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // Storage blocked: the in-memory choice above still switches the app.
  }
  window.dispatchEvent(new Event(CHANGED));
}

type I18n = { lang: Lang; setLang: (l: Lang) => void; t: (text: string, vars?: Vars) => string };
const Ctx = createContext<I18n>({ lang: "en", setLang: () => {}, t: (s, v) => translate(s, "en", v) });

/**
 * The traveller's language, kept in this browser. Prerendered pages start in
 * English and switch on load. Sets <html lang> and data-lang, which picks the
 * Anek font for Indic scripts (ty.css).
 */
export function LangProvider({ children }: { children: React.ReactNode }) {
  const lang = useSyncExternalStore(subscribe, readLang, () => "en" as Lang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dataset.lang = lang;
  }, [lang]);
  const setLang = useCallback((l: Lang) => saveLang(l), []);
  const value = useMemo(() => ({ lang, setLang, t: (s: string, v?: Vars) => translate(s, lang, v) }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);
