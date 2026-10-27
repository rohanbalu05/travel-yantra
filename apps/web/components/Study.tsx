"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { studyTasks, type Study, type StudyTask } from "@/lib/metrics";

/** Task and arm from the study link; organisers open /study/?task=plan_goa_family&arm=ty for each participant. */
export function useStudyParams(): Study {
  const params = useSearchParams();
  const task = (params.get("task") ?? "plan_trip").replace(/[^a-z0-9_-]/gi, "").slice(0, 40) || "plan_trip";
  const arm: Study["arm"] = params.get("arm") === "baseline" ? "baseline" : "ty";
  return { task, arm };
}

/** The brief for a task (TY3's GET /routes/metrics/tasks), once loaded. */
export function useTaskBrief(task: string): StudyTask | null {
  const [found, setFound] = useState<StudyTask | null>(null);
  useEffect(() => {
    let live = true;
    void studyTasks().then((list) => live && setFound(list.find((x) => x.id === task) ?? null));
    return () => {
      live = false;
    };
  }, [task]);
  return found;
}

/** The baseline arm must not use Travel Yantra, so its screens have no app navigation. */
export function StudyFrame({ arm, children }: { arm: Study["arm"]; children: React.ReactNode }) {
  if (arm === "ty") return <AppShell>{children}</AppShell>;
  return (
    <main className="app-main">
      <div className="wrap" style={{ display: "flex", flexDirection: "column", gap: 24 }}>{children}</div>
    </main>
  );
}
