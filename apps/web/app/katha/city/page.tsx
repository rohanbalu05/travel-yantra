"use client";

import { Suspense } from "react";
import { KathaSubject } from "@/components/KathaSubject";

export default function Page() {
  return (
    <Suspense>
      <KathaSubject kind="city" fallback="Mysuru" />
    </Suspense>
  );
}
