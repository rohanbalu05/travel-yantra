"use client";

import { useCallback, useEffect, useReducer, useRef, useState, useSyncExternalStore } from "react";
import type { Itinerary, Lang } from "@/lib/contracts";
import { chatAvailable, type ChatEvent, streamChat } from "./chatClient";
import styles from "./ChatPanel.module.css";
import { EMPTY, type Line, pieces, reduce } from "./chatState";
import { type Listening, listen, speechAvailable } from "./speech";
import { say } from "./strings";

export type PlanChanged = { plan_id: string; share_token?: string; itinerary: Itinerary };

export type ChatPanelProps = {
  /** The plan the page shows; chat edits apply to it. */
  planId: string | null;
  /** Its share token, when the page has one (lets the chat open a plan this browser did not make). */
  shareToken?: string | null;
  lang: Lang;
  /** A chat edit or a new plan finished: replace the plan on the page with this one. */
  onPlanChanged?: (e: PlanChanged) => void;
};

/** The chat assistant: plan a trip, change the plan in plain words, ask the guide. Streams replies from POST /chat. */
export function ChatPanel({ planId, shareToken = null, lang, onPlanChanged }: ChatPanelProps) {
  const [state, dispatch] = useReducer(reduce, EMPTY);
  const [draft, setDraft] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  // False on the server and in the first render; the browser's answer after hydration.
  const canSpeak = useSyncExternalStore(noSubscribe, speechAvailable, () => false);
  const mic = useRef<Listening | null>(null);
  const abort = useRef<AbortController | null>(null);
  const log = useRef<HTMLOListElement>(null);
  const changed = useRef(onPlanChanged);
  useEffect(() => {
    changed.current = onPlanChanged;
  });
  const live = chatAvailable();

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    const el = log.current;
    if (el && typeof el.scrollTo === "function") el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [state.lines.length]);

  const send = useCallback(
    async (text: string) => {
      const words = text.trim();
      if (!words || state.busy || !live) return;
      setDraft("");
      setVoiceNote(null);
      dispatch({ kind: "sent", text: words });
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      const onEvent = (event: ChatEvent) => {
        dispatch({ kind: "event", event });
        if (event.type === "plan" && event.plan_id && event.itinerary) {
          changed.current?.({ plan_id: event.plan_id, share_token: event.share_token, itinerary: event.itinerary });
        }
      };
      try {
        await streamChat({ text: words, lang, plan_id: planId, share_token: shareToken }, onEvent, ctl.signal);
        dispatch({ kind: "event", event: { type: "done" } });
      } catch (e) {
        if (ctl.signal.aborted) return;
        dispatch({ kind: "failed", text: say("failed", lang) + (e instanceof Error && e.message ? ` (${e.message})` : "") });
      }
    },
    [lang, live, planId, shareToken, state.busy],
  );

  const toggleMic = () => {
    if (listening) {
      mic.current?.stop();
      return;
    }
    if (!canSpeak) {
      setVoiceNote(say("noVoice", lang));
      return;
    }
    setVoiceNote(null);
    setListening(true);
    mic.current = listen(
      lang,
      (words) => setDraft(words),
      (words, error) => {
        setListening(false);
        mic.current = null;
        if (words) void send(words);
        else if (error === "not-allowed" || error === "service-not-allowed") setVoiceNote(say("micBlocked", lang));
        else if (error === "unsupported") setVoiceNote(say("noVoice", lang));
        else setVoiceNote(say("notHeard", lang));
      },
    );
  };

  return (
    <section className={styles.panel} aria-label={say("title", lang)}>
      <h2 className={styles.title}>{say("title", lang)}</h2>
      <ol className={styles.log} ref={log} aria-live="polite" aria-busy={state.busy}>
        {!live && <li className={styles.note}>{say("offline", lang)}</li>}
        {state.lines.map((line) => (
          <li key={line.id} className={styles[line.role]}>
            <LineView line={line} lang={lang} />
          </li>
        ))}
      </ol>
      {state.chips.length > 0 && !state.busy && (
        <div className={styles.chips}>
          {state.chips.map((c) => (
            <button key={c} type="button" className={styles.chip} onClick={() => (c.includes("<") ? setDraft(c.replace(/<[^>]*>/, "").trim() + " ") : void send(c))}>
              {c}
            </button>
          ))}
        </div>
      )}
      {voiceNote && (
        <p className={styles.voiceNote} role="status">
          {voiceNote}
        </p>
      )}
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <label className={styles.hidden} htmlFor="ty-chat-input">
          {say("placeholder", lang)}
        </label>
        <textarea
          id="ty-chat-input"
          className={styles.input}
          value={draft}
          rows={1}
          maxLength={4000}
          placeholder={listening ? say("listening", lang) : say("placeholder", lang)}
          disabled={!live}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send(draft);
            }
          }}
        />
        <button
          type="button"
          className={`${styles.mic} ${listening ? styles.on : ""}`}
          onClick={toggleMic}
          disabled={!live || state.busy}
          aria-pressed={listening}
          aria-label={listening ? say("stop", lang) : say("speak", lang)}
          title={canSpeak ? say("speak", lang) : say("noVoice", lang)}
        >
          <MicIcon />
        </button>
        <button type="submit" className={styles.send} disabled={!live || state.busy || !draft.trim()}>
          {say("send", lang)}
        </button>
      </form>
    </section>
  );
}

function LineView({ line, lang }: { line: Line; lang: Lang }) {
  switch (line.role) {
    case "user":
      return (
        <>
          <span className={styles.who}>{say("you", lang)}</span>
          <p>{line.text}</p>
        </>
      );
    case "heard":
      return (
        <>
          <span className={styles.who}>{say("heard", lang)}</span>
          <p>“{line.text}”</p>
        </>
      );
    case "updated":
      return <p>{say("updated", lang)}</p>;
    case "audio":
      return (
        <>
          <span className={styles.who}>{say("story", lang)}{line.text ? ` · ${line.text}` : ""}</span>
          <audio controls preload="none" src={line.url} className={styles.audioEl} />
        </>
      );
    default:
      return (
        <p>
          {pieces(line.text).map((p, i) =>
            p.href ? (
              <a key={i} href={p.href} target="_blank" rel="noopener noreferrer">
                {shortLink(p.href)}
              </a>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
      );
  }
}

/** "maps.google.com/?q=15.5,73.9" rather than the whole URL on a phone. */
function shortLink(href: string): string {
  try {
    const u = new URL(href);
    const rest = (u.pathname === "/" ? "" : u.pathname) + u.search;
    return u.host.replace(/^www\./, "") + (rest.length > 28 ? rest.slice(0, 27) + "…" : rest);
  } catch {
    return href;
  }
}

const noSubscribe = () => () => {};

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

export default ChatPanel;
