"use client";

import Link from "next/link";
import { Fragment } from "react";
import { useI18n } from "@/lib/i18n";

const STEPS: [string, string | null][] = [
  ["Describe", "/plan/start/"],
  ["Plan", "/plan/thinking/"],
  ["Choose a way", "/plan/options/"],
  ["Itinerary", "/plan/itinerary/"],
  ["Book", "/book/"],
  ["Katha", "/katha/"],
];

/** The six planning steps; `at` is the current one (1-based). Earlier steps link back. */
export function Trail({ at }: { at: number }) {
  const { t } = useI18n();
  return (
    <nav className="trail" aria-label={t("Planning steps")}>
      {STEPS.map(([label, href], i) => {
        const n = i + 1;
        const inner = (
          <>
            <i>{n}</i>
            {t(label)}
          </>
        );
        return (
          <Fragment key={label}>
            {n < at && href ? (
              <Link className="done" href={href}>{inner}</Link>
            ) : (
              <span className={n === at ? "on" : undefined} aria-current={n === at ? "step" : undefined}>{inner}</span>
            )}
            {n < STEPS.length && <span className="sep" />}
          </Fragment>
        );
      })}
    </nav>
  );
}
