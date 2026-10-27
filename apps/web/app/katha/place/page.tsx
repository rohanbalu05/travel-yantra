"use client";

import { Suspense } from "react";
import { KathaSubject } from "@/components/KathaSubject";

export default function Page() {
  return (
    <Suspense>
      <KathaSubject kind="place" fallback="Basilica of Bom Jesus" />
    </Suspense>
  );
}
