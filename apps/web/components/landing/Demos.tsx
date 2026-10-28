"use client";

// Landing demos, from components/LandingInteractive.tsx (TY4), with the copy
// kept to what the product does today.

import Link from "next/link";
import { useState } from "react";
import { Logo } from "@/components/Brand";

const bar = (title: string, tag: string) => (
  <div className="demo-bar"><Logo />{title}<span>{tag}</span></div>
);
const Row = ({ t, s, st, ok }: { t: string; s: string; st: string; ok?: boolean }) => (
  <div className="d-row"><div><b>{t}</b><small>{s}</small></div><span className={ok ? "d-ok" : "d-wait"}>{st}</span></div>
);

const STEPS = [
  { h: "Say it the way you would say it to a friend.", p: "Type in any of six languages, or mix them. Dates, people, budget, food and pace are picked out for you to check." },
  { h: "Watch it plan.", p: "Four specialists work at once: transport, places, stays and stories. Every stop is checked against opening hours, closing days, travel time, meals and your budget." },
  { h: "Pick a way to go.", p: "Road, rail or air, compared on time, cost and comfort for the people you are travelling with, with a clear recommendation and the reason for it." },
  { h: "Change anything by asking.", p: "Say it should be lighter, cheaper or more about temples. Only the day you touched is rebuilt, and you are told exactly what moved." },
  { h: "Book with the official sellers.", p: "Trains on IRCTC, with every detail ready to copy across. Flights and stays on the airline and booking sites, opened with your dates filled in." },
  { h: "Go with a guide that tells the story.", p: "Each place has its Katha, to read or hear in your language. On the day, the live trip page shows where you are against the plan and what is near you." },
];

const chips = ["Bengaluru to Goa", "Fri 11 to Mon 14 Dec", "4 travellers, one over 60", "Churches and temples", "Some beach time", "Vegetarian", "About ₹60,000 in all", "Gentle pace"];

const FRAMES = [
  <div className="demo" key="1">
    {bar("New trip", "Hinglish")}
    <div className="demo-body">
      <div className="d-user">Goa jaana hai 11 se 14 Dec, mummy papa aur behen ke saath. Churches aur temples, thoda beach. Veg khana, budget 60 hazaar.</div>
      <div className="d-label">We understood</div>
      <div className="d-chips">{chips.map((c) => <span className="d-chip" key={c}>{c}</span>)}</div>
      <div className="d-note">Anything wrong? Tap a detail to change it before we plan.</div>
    </div>
  </div>,
  <div className="demo" key="2">
    {bar("Planning your Goa trip", "12 seconds")}
    <div className="demo-body">
      <Row t="Transport" s="Road, rail and air compared door to door" st="Done" ok />
      <Row t="Places" s="14 chosen from 142, grouped into four easy days" st="Done" ok />
      <Row t="Stays" s="Panaji is closest to all four days" st="Done" ok />
      <Row t="Katha" s="14 stories ready, 4 of them legends" st="Writing" />
      <div className="d-note">41 of 41 checks passed: hours, closing days, travel time, meals, day ends by 7 pm, budget.</div>
    </div>
  </div>,
  <div className="demo" key="3">
    {bar("Three ways to Goa", "For 4, return")}
    <div className="demo-body">
      <table className="d-table">
        <thead><tr><th>Way</th><th>Door to door</th><th>Whole trip (est.)</th><th>For Papa</th></tr></thead>
        <tbody>
          <tr><td><b>Fly to Mopa</b></td><td>4½ h</td><td>₹86,700</td><td>Easiest</td></tr>
          <tr className="pick"><td><b>Rail past Dudhsagar</b> <span className="d-pill">Picked</span></td><td>12 h, overnight</td><td>₹57,400</td><td>Lower berth</td></tr>
          <tr><td><b>Road via Hubballi</b></td><td>10 to 11 h</td><td>₹55,800</td><td>Long day</td></tr>
        </tbody>
      </table>
      <div className="d-ai">Rail fits your budget with room to spare, Papa gets a lower berth, and you pass Dudhsagar at breakfast time.</div>
    </div>
  </div>,
  <div className="demo" key="4">
    {bar("Goa with family", "Saturday")}
    <div className="demo-body">
      <div className="d-user">Make Saturday lighter, Papa gets tired by afternoon.</div>
      <div className="d-ai">Done. Saturday now ends at 4 pm. I took out the Shantadurga temple and moved the spice farm lunch half an hour earlier. Friday, Sunday and Monday are unchanged.</div>
      <Row t="Saturday" s="5 stops, ends 4:00 pm, 12 km less in the cab" st="Rebuilt" ok />
      <Row t="Friday, Sunday, Monday" s="Exactly as before" st="Unchanged" ok />
    </div>
  </div>,
  <div className="demo" key="5">
    {bar("Bookings", "3 of 5 done")}
    <div className="demo-body">
      <Row t="Train out, Thu 10 Dec" s="IRCTC, 3A, four berths" st="Confirmed" ok />
      <Row t="Stay in Panaji, 3 nights" s="Booking.com, two rooms" st="Booked" ok />
      <Row t="Train back, Mon 14 Dec" s="Waitlist 12" st="Waiting" />
      <Row t="Day cab, Saturday" s="Goa licensed taxi, about ₹2,600" st="To book" />
    </div>
  </div>,
  <div className="demo" key="6">
    {bar("Now at Shri Mangueshi Temple", "2 min")}
    <div className="demo-body">
      <div className="d-label">Place Katha, in Hindi</div>
      <p className="hi" style={{ margin: 0, fontSize: 19, lineHeight: 1.6 }}>कहते हैं, एक बार शिव ने बाघ का रूप लेकर पार्वती को डराया। घबराकर पार्वती ने पुकारा, &quot;त्राहि माम् गिरीश&quot;। वही शब्द यहाँ देवता का नाम बन गए: मंगेश।</p>
      <div className="d-chips"><span className="tag tag-legend">Legend</span><span className="tag tag-history">History next: why the temple moved inland in 1560</span></div>
      <div className="d-note">Read it or play it. Next stop: spice farm lunch, 6 km.</div>
    </div>
  </div>,
];

/** Steps on the left; the chosen step's demo on the right. */
export function HowItWorks() {
  const [i, setI] = useState(0);
  return (
    <div className="two">
      <div>
        {STEPS.map((s, k) => (
          <button type="button" key={s.h} className={`step${k === i ? " on" : ""}`} aria-pressed={k === i} onClick={() => setI(k)}>
            <span className="step-n">0{k + 1}</span>
            <h3>{s.h}</h3>
            <p>{s.p}</p>
          </button>
        ))}
      </div>
      <div className="how-demo" aria-live="polite">{FRAMES[i]}</div>
    </div>
  );
}

const L = {
  en: { label: "English", cls: "", say: "Plan a Goa trip for me and my parents.", reply: "Here are three ways to get to Goa." },
  kn: { label: "ಕನ್ನಡ", cls: "kn", say: "ನನಗೂ ನನ್ನ ಅಪ್ಪ ಅಮ್ಮನಿಗೂ ಒಂದು ಗೋವಾ ಪ್ರವಾಸ ಪ್ಲಾನ್ ಮಾಡು.", reply: "ಗೋವಾ ತಲುಪಲು ಮೂರು ದಾರಿಗಳು ಇಲ್ಲಿವೆ." },
  hi: { label: "हिन्दी", cls: "hi", say: "मेरे और मेरे माता-पिता के लिए गोवा की यात्रा प्लान करो।", reply: "गोवा पहुँचने के तीन रास्ते ये रहे।" },
  ta: { label: "தமிழ்", cls: "ta", say: "எனக்கும் என் அப்பா அம்மாவுக்கும் ஒரு கோவா பயணம் திட்டமிடு.", reply: "கோவா செல்ல மூன்று வழிகள் இதோ." },
  te: { label: "తెలుగు", cls: "te", say: "నాకూ మా అమ్మానాన్నలకూ ఒక గోవా ట్రిప్ ప్లాన్ చెయ్యి.", reply: "గోవాకు వెళ్ళడానికి మూడు దారులు ఇవిగో." },
  bn: { label: "বাংলা", cls: "bn", say: "আমার আর আমার বাবা-মায়ের জন্য একটা গোয়া ট্রিপ প্ল্যান করো।", reply: "গোয়া যাওয়ার তিনটে উপায় এই রইল।" },
  mix: { label: "Hinglish", cls: "", say: "Mere aur mummy papa ke liye Goa trip plan karo.", reply: "Goa jaane ke teen raaste ye rahe." },
};
type LangKey = keyof typeof L;

export function LanguageDemo() {
  const [k, setK] = useState<LangKey>("en");
  const x = L[k];
  return (
    <div className="lang-wrap">
      <div>
        <div className="sec-head" style={{ marginBottom: 0 }}>
          <p className="kicker">Six languages</p>
          <h2>Plan in the language you think in.</h2>
          <p>Type in Kannada, Hindi, Tamil, Telugu, Bengali or English. Mix them the way you talk, or type Hinglish and Kanglish in English letters. Plans, replies and every Katha come back in the same language.</p>
        </div>
        <div className="lang-list" role="group" aria-label="Pick a language">
          {(Object.keys(L) as LangKey[]).map((n) => (
            <button type="button" key={n} className={`lang-btn ${L[n].cls}${n === k ? " on" : ""}`} onClick={() => setK(n)}>{L[n].label}</button>
          ))}
        </div>
      </div>
      <div className="lang-stage">
        <span className="lang-who">You say</span>
        <p className={`lang-say ${x.cls}`}>{x.say}</p>
        <span className="lang-who">Travel Yantra replies</span>
        <p className={`lang-reply ${x.cls}`}>{x.reply}</p>
        <p className="lang-foot">Replies in all six languages: on the web, on WhatsApp (typed or as a voice note) and through the MCP server.</p>
      </div>
    </div>
  );
}

type SegRow = [string, string];
const T = (c: string): string => `tag tag-${c}`;
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
const KATHA: Record<string, { name: string; title: string; meta: string; tag: string; quote: string; rows: SegRow[] }> = {
  city: {
    name: "City", title: "Mysuru in 5 minutes", meta: "City Katha, 7 parts, English", tag: "legend",
    quote: "As the story goes, the goddess Chamundeshwari fought the buffalo demon Mahishasura on the hill above the city. The town took his name, Mahishuru, and in time became Mysuru.",
    rows: [["What Mysuru is", "history"], ["How it got its name", "legend"], ["Who built the city you see", "history"], ["The palace", "history"], ["What it eats", "food"]],
  },
  place: {
    name: "Place", title: "Shri Mangueshi Temple", meta: "Place Katha, Ponda, Goa", tag: "legend",
    quote: "As the story goes, Shiva once took the form of a tiger to tease Parvati. Frightened, she cried out \"Trahi mam Girisha\", save me, lord of the mountain. Those words became the name of the god here: Manguesh.",
    rows: [["The tiger on the hill", "legend"], ["Why the temple moved inland", "history"], ["The seven storey lamp tower", "history"], ["Before you go in", "practical"]],
  },
  day: {
    name: "Day", title: "Saturday in Old Goa and Ponda", meta: "Day Katha, 5 stops", tag: "history",
    quote: "Plays stop by stop as you arrive, starting with the Basilica of Bom Jesus at 9:00. Saved on your phone, so it works with no signal.",
    rows: [["Basilica of Bom Jesus", "history"], ["Sé Cathedral", "history"], ["Church of St Francis of Assisi", "history"], ["Shri Mangueshi Temple", "legend"], ["Spice farm lunch", "food"]],
  },
};

/** A look at the three kinds of Katha; the real player is on /katha/. */
export function KathaPreview() {
  const [tab, setTab] = useState("city");
  const k = KATHA[tab];
  return (
    <div className="player">
      <div className="seg" role="group" aria-label="Kind of Katha">
        {Object.entries(KATHA).map(([id, v]) => (
          <button type="button" key={id} className={id === tab ? "on" : undefined} aria-pressed={id === tab} onClick={() => setTab(id)}>{v.name}</button>
        ))}
      </div>
      <div className="player-top">
        <div className="player-title"><b>{k.title}</b><span>{k.meta}</span></div>
      </div>
      <p className="quote"><span className={T(k.tag)}>{cap(k.tag)}</span>{k.quote}</p>
      <div>
        {k.rows.map(([title, tag], n) => (
          <div className="segrow" key={title}>
            <span className="n">{n + 1}</span><span>{title}</span>
            <span className={T(tag)}>{cap(tag)}</span>
          </div>
        ))}
      </div>
      <Link className="btn btn-cream btn-sm" href="/katha/city/" style={{ alignSelf: "flex-start" }}>Hear a Katha</Link>
    </div>
  );
}
