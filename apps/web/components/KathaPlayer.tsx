"use client";

import { useEffect, useRef, useState } from "react";
import { PlayIcon } from "@/components/Wave";
import type { KathaAudio } from "@/lib/contracts";
import { useI18n } from "@/lib/i18n";

export const SPEEDS = [0.75, 1, 1.25, 1.5] as const;

const mmss = (s: number) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");

/**
 * TY2's read-aloud Katha: one MP3 per chapter, played in chapter order, back to
 * back (each already ends on a pause). Never starts by itself; nothing loads
 * until Play. Play, pause, seek within the part, previous and next part, speed.
 */
export function KathaPlayer({ audio }: { audio: KathaAudio[] }) {
  const { t } = useI18n();
  const parts = [...audio].sort((a, b) => a.chapter - b.chapter);
  const el = useRef<HTMLAudioElement>(null);
  const [part, setPart] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);
  const [speed, setSpeed] = useState<number>(1);
  const [failed, setFailed] = useState(false);
  // Nothing loads until the first Play; after that each next part may load by itself.
  const [started, setStarted] = useState(false);
  // Moving to another part while playing keeps playing, once that part can play.
  const keepPlaying = useRef(false);

  useEffect(() => {
    if (el.current) el.current.playbackRate = speed;
  }, [speed]);

  if (!parts.length) return null;
  const go = (i: number, keep = playing) => {
    keepPlaying.current = keep;
    setAt(0);
    setLength(0);
    setPart(i);
  };
  const toggle = () => {
    const a = el.current;
    if (!a) return;
    if (a.paused) {
      setFailed(false);
      setStarted(true);
      a.play().catch(() => setFailed(true));
    } else a.pause();
  };

  return (
    <div className="kap" role="group" aria-label={t("Listen to the Katha")}>
      <audio
        ref={el}
        src={parts[part].url}
        preload={started ? "auto" : "none"}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => setAt(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => {
          setLength(e.currentTarget.duration);
          e.currentTarget.playbackRate = speed;
        }}
        onCanPlay={(e) => {
          // A new part has loaded: play on only if the last one was playing.
          if (!keepPlaying.current) return;
          keepPlaying.current = false;
          e.currentTarget.play().catch(() => setPlaying(false));
        }}
        onEnded={() => {
          if (part + 1 < parts.length) go(part + 1, true);
        }}
        onError={() => setFailed(true)}
      />
      <button type="button" className="kp-play" onClick={toggle} aria-label={playing ? t("Pause the Katha") : t("Play the Katha")}>
        <PlayIcon playing={playing} />
      </button>
      <div className="kap-main">
        <input
          type="range"
          className="kap-seek"
          min={0}
          max={length || 0}
          step={1}
          value={Math.min(at, length || 0)}
          disabled={!length}
          aria-label={t("Position in part {n}", { n: part + 1 })}
          aria-valuetext={`${mmss(at)} / ${mmss(length)}`}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (el.current) el.current.currentTime = v;
            setAt(v);
          }}
        />
        <div className="kap-row">
          <span className="kap-time">{mmss(at)} / {mmss(length)}</span>
          {parts.length > 1 && (
            <span className="kap-parts">
              <button type="button" className="btn btn-quiet btn-sm" disabled={part === 0} onClick={() => go(part - 1)} aria-label={t("Previous part")}>‹</button>
              <span>{t("Part {n} of {total}", { n: part + 1, total: parts.length })}</span>
              <button type="button" className="btn btn-quiet btn-sm" disabled={part + 1 >= parts.length} onClick={() => go(part + 1)} aria-label={t("Next part")}>›</button>
            </span>
          )}
          <label className="kap-speed">
            <span>{t("Speed")}</span>
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
              {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
        </div>
        {failed && <p className="hint" role="alert">{t("The audio could not play. The story is below to read.")}</p>}
      </div>
    </div>
  );
}
