"use client";

import Link from "next/link";
import { Fragment } from "react";
import { useI18n } from "@/lib/i18n";
import { usePlanInput, usePlanResult } from "@/lib/plan";

const STEPS: [string, string | null][] = [
  ["Describe", "/plan/start/"],
  ["Plan", "/plan/thinking/"],
  ["Choose a way", "/plan/options/"],
  ["Itinerary", "/plan/itinerary/"],
  ["Book", "/book/"],
  ["Katha", "/katha/day/"],
];

/**
 * The six planning steps; `at` is the current one (1-based). Every step that has something
 * to show links: Describe once there is input, and the rest once a plan is ready. "Plan"
 * itself links only before a result exists, since opening it plans again.
 */
export function Trail({ at }: { at: number }) {
  const { t } = useI18n();
  const hasInput = !!usePlanInput();
  const hasPlan = !!usePlanResult();
  const reachable = (n: number) => (n === 1 ? hasInput || n < at : n === 2 ? !hasPlan && n < at : hasPlan || n < at);
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
            {n !== at && href && reachable(n) ? (
              <Link className={n < at ? "done" : undefined} href={href}>{inner}</Link>
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
