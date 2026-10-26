import Link from "next/link";
import { SCREENS } from "@/lib/screens";

export default function Landing() {
  return (
    <>
      <p className="eyebrow">Travel Yantra</p>
      <h1>Your whole journey, planned and told.</h1>
      <p>Plan multi-city trips across India, compare road, rail and air, and hear the story of every place.</p>
      <p>
        <Link className="button" href="/plan/start/">Plan a trip</Link>
      </p>
      <h2>All screens</h2>
      <ul className="screen-list">
        {SCREENS.filter((s) => s.slug !== "landing").map((s) => (
          <li key={s.slug}>
            <Link href={s.path}>
              {s.title}
              <small>{s.blurb}</small>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
