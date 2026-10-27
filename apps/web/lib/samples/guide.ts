import type { GuideAnswer, GuideQuestion, KathaStory } from "@/lib/contracts";

// Sample answers and stories for the mock mode. Short, sourced, and labelled as sample in the UI.

const WIKI_BOM = "https://en.wikipedia.org/wiki/Basilica_of_Bom_Jesus";
const WIKI_XAVIER = "https://en.wikipedia.org/wiki/Francis_Xavier";
const WIKI_MYSURU = "https://en.wikipedia.org/wiki/Mysore";
const WIKI_CHAMUNDI = "https://en.wikipedia.org/wiki/Chamundi_Hills";

const EMERGENCY = /hospital|doctor|police|pharmacy|chemist|medical|emergency|ambulance/i;

export function sampleAnswer(q: GuideQuestion): GuideAnswer {
  const lang = q.lang ?? "en";
  if (EMERGENCY.test(q.question)) {
    return {
      text: "Call 112 for any emergency in India. The nearest large hospital to Old Goa is Goa Medical College at Bambolim [1]. For police, the Old Goa police station is close to the churches.",
      citations: [{ title: "Goa Medical College (Wikipedia)", url: "https://en.wikipedia.org/wiki/Goa_Medical_College" }],
      emergency_places: [
        { id: "sample-gmc", name: "Goa Medical College and Hospital", lat: 15.4547, lng: 73.8574, category: "hospital", typical_visit_minutes: 0, source: "sample" },
        { id: "sample-old-goa-police", name: "Old Goa Police Station", lat: 15.5032, lng: 73.9125, category: "police", typical_visit_minutes: 0, source: "sample" },
      ],
      lang,
    };
  }
  if (/bom jesus|xavier|basilica/i.test(q.question) || q.place_name === "Basilica of Bom Jesus") {
    return {
      text: "The Basilica of Bom Jesus in Old Goa was completed in 1605 [1]. It holds the remains of St Francis Xavier, which are shown to the public about once a decade [1][2]. Dress modestly and keep quiet inside; it is a working church.",
      citations: [
        { title: "Basilica of Bom Jesus (Wikipedia)", url: WIKI_BOM },
        { title: "Francis Xavier (Wikipedia)", url: WIKI_XAVIER },
      ],
      emergency_places: [],
      lang,
    };
  }
  return { text: "I don't have a sourced answer for that yet, so I won't guess. Try asking about a place on your plan.", citations: [], emergency_places: [], lang };
}

type Seg = { label: "legend" | "history"; text: string };

const STORIES: Record<string, { sources: string[]; segs: Seg[] }> = {
  "basilica of bom jesus": {
    sources: [WIKI_BOM, WIKI_XAVIER],
    segs: [
      { label: "history", text: "Jesuits finished the Basilica of Bom Jesus in 1605, when Old Goa was the capital of Portuguese India [1]." },
      { label: "history", text: "Its name means 'Good Jesus', the infant Jesus. The front mixes Doric, Ionic and Corinthian styles in black basalt, once covered in lime plaster [1]." },
      { label: "legend", text: "As the story goes, when Francis Xavier's body reached Goa from China in 1554, it had not decayed, and pilgrims took this as a sign of his holiness [2]." },
      { label: "history", text: "The remains rest in a silver casket above a marble tomb gifted by the Medici Grand Duke of Tuscany [1]." },
      { label: "legend", text: "As the story goes, a devotee bit off one of the saint's toes to keep as a relic; it is a tale told at the church to this day [2]." },
    ],
  },
  goa: {
    sources: ["https://en.wikipedia.org/wiki/Goa", "https://en.wikipedia.org/wiki/Velha_Goa"],
    segs: [
      { label: "history", text: "The Portuguese took Goa in 1510 and ruled it for over four centuries, until 1961 [1]." },
      { label: "history", text: "Old Goa, once larger than Lisbon by some accounts, was left after epidemics; Panaji became the capital in 1843 [2]." },
      { label: "legend", text: "As the story goes, the god Parashurama shot an arrow into the sea and the waters drew back to make the land of Goa [1]." },
    ],
  },
  mysuru: {
    sources: [WIKI_MYSURU, WIKI_CHAMUNDI],
    segs: [
      { label: "history", text: "Mysuru was the seat of the Wodeyar kings, who ruled the Kingdom of Mysore for most of five centuries [1]." },
      { label: "legend", text: "As the story goes, the goddess Chamundeshwari killed the buffalo demon Mahishasura on the hill above the city, which gave Mysuru its name [2]." },
      { label: "history", text: "The Dasara festival, with its procession of elephants, has been held in the city since the Vijayanagara era [1]." },
    ],
  },
};

const SEGS_FOR: Record<2 | 5 | 10, number> = { 2: 2, 5: 3, 10: 5 };

/** A day's sample story: the known stops' stories in order, sources renumbered. */
function dayStory(places: string[]): { sources: string[]; segs: Seg[] } | undefined {
  const sources: string[] = [];
  const segs: Seg[] = [];
  for (const p of places) {
    const s = STORIES[p.toLowerCase()];
    if (!s) continue;
    const at = (n: number) => {
      const src = s.sources[n - 1];
      if (!sources.includes(src)) sources.push(src);
      return sources.indexOf(src) + 1;
    };
    for (const g of s.segs) segs.push({ ...g, text: g.text.replace(/\[(\d+)\]/g, (_, n) => `[${at(Number(n))}]`) });
  }
  return segs.length ? { sources, segs } : undefined;
}

/** A sample story; unknown subjects get a short honest placeholder rather than made-up history. */
export function sampleKatha(kind: KathaStory["subject_kind"], subject: string, length: 2 | 5 | 10, lang: KathaStory["lang"] = "en", places: string[] = []): KathaStory {
  const s = kind === "day" ? dayStory(places) : STORIES[subject.toLowerCase()];
  if (!s) {
    return {
      subject_kind: kind,
      subject,
      length_min: length,
      text: `We do not have a sourced story for ${subject} yet.`,
      segments: [],
      sources: [],
      lang,
    };
  }
  const segs = s.segs.slice(0, SEGS_FOR[length]);
  return { subject_kind: kind, subject, length_min: length, text: segs.map((x) => x.text).join(" "), segments: segs, sources: s.sources, lang };
}
