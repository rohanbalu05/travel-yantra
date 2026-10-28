import type { Lang } from "@/lib/contracts";

/** Browser speech recognition locales for the six languages. */
export const SPEECH_LANG: Record<Lang, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
  ta: "ta-IN",
  te: "te-IN",
  bn: "bn-IN",
};

type Result = { 0: { transcript: string }; isFinal: boolean };
type RecognitionEvent = { results: ArrayLike<Result> };
type Recognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};
type RecognitionCtor = new () => Recognition;

function ctor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Chrome, Edge and Safari have it; Firefox does not. */
export const speechAvailable = () => ctor() !== null;

export type Listening = { stop(): void };

/**
 * Listens once in `lang`. onText gets the words so far (interim, then final); onEnd gets the final words, or an
 * error code ("not-allowed" when the microphone is blocked, "no-speech", "network", "unsupported").
 */
export function listen(lang: Lang, onText: (words: string) => void, onEnd: (words: string, error?: string) => void): Listening | null {
  const Ctor = ctor();
  if (!Ctor) {
    onEnd("", "unsupported");
    return null;
  }
  const rec = new Ctor();
  rec.lang = SPEECH_LANG[lang] ?? "en-IN";
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  let words = "";
  let error: string | undefined;
  rec.onresult = (e) => {
    words = Array.from(e.results, (r) => r[0].transcript).join(" ").trim();
    onText(words);
  };
  rec.onerror = (e) => {
    error = e.error;
  };
  rec.onend = () => onEnd(words, words ? undefined : (error ?? "no-speech"));
  try {
    rec.start();
  } catch {
    onEnd("", "unsupported");
    return null;
  }
  return { stop: () => rec.stop() };
}
