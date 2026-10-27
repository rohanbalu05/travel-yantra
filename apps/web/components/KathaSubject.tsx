"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { KathaView } from "@/components/KathaView";
import "@/app/guide.css";

/** A place or city Katha page; the subject comes from ?subject=. */
export function KathaSubject({ kind, fallback }: { kind: "place" | "city"; fallback: string }) {
  const subject = useSearchParams().get("subject")?.trim() || fallback;
  return (
    <AppShell>
      <div>
        <nav className="crumbs" aria-label="Breadcrumb" style={{ marginBottom: 12, fontSize: 14 }}>
          <Link href="/katha/">Katha</Link> · <span>{kind === "city" ? "City" : "Place"}</span>
        </nav>
        <div className="k-head">
          <h1 className="page-title">{subject}</h1>
          <p className="page-sub">{kind === "city" ? "The city's story, from its founding to today." : "The story of this place, history first, legends labelled."}</p>
        </div>
        <KathaView key={`${kind}:${subject}`} req={{ subject_kind: kind, subject, lang: "en" }} />
        <p style={{ marginTop: 24 }}>
          <Link className="btn btn-quiet btn-sm" href="/ask/">Ask the guide about {subject}</Link>
        </p>
      </div>
    </AppShell>
  );
}
