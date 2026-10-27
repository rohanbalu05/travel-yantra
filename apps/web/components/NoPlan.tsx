import Link from "next/link";

/** Shown when a plan screen opens with no finished plan in this tab. */
export function NoPlan() {
  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
      <h1 className="h2" style={{ margin: 0 }}>No plan yet</h1>
      <p className="page-sub" style={{ margin: 0 }}>Plans live in this browser tab until you save them. Start one and it will show up here.</p>
      <Link className="btn btn-primary" href="/plan/start/">Plan a trip</Link>
    </section>
  );
}
