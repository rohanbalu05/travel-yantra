const HEIGHTS = [38, 62, 80, 54, 92, 70, 44, 66, 88, 58, 74, 40, 96, 64, 50, 82, 60, 72, 46, 90, 56, 68, 84, 42, 76, 52, 94, 62, 48, 78, 58, 70, 40, 86, 64, 52, 74, 60, 90, 48];

/** Decorative waveform bars; `play` animates them. */
export function Wave({ play, count = 32, step = 0.13 }: { play?: boolean; count?: number; step?: number }) {
  return (
    <div className={play ? "wave play" : "wave"} aria-hidden="true">
      {HEIGHTS.slice(0, count).map((h, i) => (
        <i key={i} style={{ height: `${h}%`, animationDelay: `${(-(i * step) % 1).toFixed(2)}s` }} />
      ))}
    </div>
  );
}

export function PlayIcon({ playing }: { playing: boolean }) {
  return (
    <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
      {playing ? (
        <>
          <rect x="6.5" y="5" width="3.6" height="14" fill="currentColor" stroke="none" />
          <rect x="13.9" y="5" width="3.6" height="14" fill="currentColor" stroke="none" />
        </>
      ) : (
        <path d="M8 5v14l11-7L8 5Z" fill="currentColor" stroke="none" />
      )}
    </svg>
  );
}
