import Link from "next/link";
import { Brand, Logo } from "@/components/Brand";
import { HowItWorks, KathaPlayer, LanguageDemo } from "@/components/LandingInteractive";
import "./landing.css";

const checks: [string, string, string][] = [
  ["Opening hours", "Every stop is open when you arrive", "14 stops checked against their hours"],
  ["Closing days", "Weekly closures and festival days", "A museum shut on Fridays moved to Saturday"],
  ["Travel time", "Between stops and between cities", "No day has more than 2 h on the road"],
  ["Meals", "A food stop that suits you, on time", "Vegetarian lunch within reach every day"],
  ["Your day's end", "When your group wants to stop", "Every day ends by 7 pm for Papa"],
  ["Walking", "For elders and small children", "Steep forts swapped for easy ones"],
  ["Season", "Monsoon closures and crowds", "Dry season, and home before the Christmas rush"],
  ["Budget", "Travel, stay, food and tickets", "₹57,400 of ₹60,000, estimated"],
];

const ways: [string, string, string, string, string][] = [
  ["Fly to Mopa", "Shortest for elders and short trips", "About 4 h with the airport", "₹19,000 to ₹26,000", "The Konkan coast from above"],
  ["Rail past Dudhsagar", "Overnight, best value", "About 12 h, you sleep through most of it", "₹5,000 to ₹6,000 in 3A", "Dudhsagar falls and the ghats"],
  ["Road via Hubballi", "Your own pace, stops on the way", "10 to 11 h of driving", "₹5,000 to ₹6,500 fuel and tolls", "The Deccan plateau, Anmod Ghat"],
];

// Web, WhatsApp, Telegram and the MCP server. Voice is cut.
const channels: [string, string, string][] = [
  ["M3 4h18v13H3zM8 21h8M12 17v4", "On the web", "The full planner with maps, side by side comparisons and the Katha library. Share a link with the family."],
  ["M4 5h16v11H9l-5 4V5Z", "On WhatsApp", "Send a message. Get the plan, map pins, the PDF and the day's Katha back in the chat."],
  ["M21 4L3 11l6 2 2 6 3-4 5 3 2-14ZM9 13l9-7", "On Telegram", "The same planner in a Telegram chat, with the same six languages."],
  ["M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16", "From your own AI assistant", "Connect the MCP server and ask for Travel Yantra plans and Katha from the tools you already use."],
];

const links = {
  Product: [["Plan a trip", "/signin/"], ["Katha library", "/katha/"], ["My trips", "/trips/"], ["On WhatsApp", "/whatsapp/"]],
  Legal: [["Terms of Service", "/legal/"], ["Privacy Policy", "/legal/"], ["Your data", "/settings/"]],
} as const;

export default function Landing() {
  return (
    <div className="site">
      <header className="sitebar">
        <Brand accent="#E07A52" />
        <nav aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#languages">Languages</a>
          <a href="#katha">Katha</a>
          <a href="#ways">Getting there</a>
        </nav>
        <div className="sb-right">
          <Link className="sb-link" href="/signin/">Sign in</Link>
          <Link className="btn btn-primary btn-sm" href="/signin/">Plan a trip</Link>
        </div>
      </header>

      <section className="hero">
        <div className="hero-in">
          <p className="hc-kicker">Plans, stories and bookings for travel in India</p>
          <h1 className="hc-title">The whole trip, in your language.</h1>
          <p className="hc-sub">Tell Travel Yantra where you want to go, in Kannada, Hindi, Tamil, Telugu, Bengali or English. It works out the route by road, rail or air, checks every stop, tells you the story of each place and lines up every booking.</p>
          <div className="hc-actions">
            <Link className="btn btn-primary" href="/signin/">Plan a trip</Link>
            <Link className="btn btn-on-dark" href="/katha/city/">Hear a Katha</Link>
          </div>
        </div>
        <div className="phone" aria-hidden="true">
          <div className="screen">
            <div className="ps-top"><Logo sw={1.8} /><span>Travel Yantra</span></div>
            <div className="ps-body">
              <div className="ps-user">Bengaluru to Goa, 11 to 14 Dec. Me, my parents and my sister. Churches, temples, a little beach. Veg food.</div>
              <div className="ps-ai">
                <b>Three ways to go</b>
                <div className="ps-row"><span>Fly to Mopa</span><span>1 h 10 m</span></div>
                <div className="ps-row"><span>Rail past Dudhsagar</span><span>overnight</span></div>
                <div className="ps-row"><span>Road via Hubballi</span><span>10 h</span></div>
              </div>
              <div className="ps-ai">Katha ready for 14 places, in all six languages.</div>
            </div>
            <div className="ps-compose">Ask or change anything</div>
          </div>
          <div className="punch" />
        </div>
      </section>

      <section className="sec sec-paper" id="how">
        <div className="wrap">
          <div className="sec-head">
            <p className="kicker">How it works</p>
            <h2>From one sentence to a trip you can take.</h2>
            <p>Talk to it the way you would talk to a friend who knows India well. The AI listens, compares and explains. Our planner checks every stop before you see the plan.</p>
          </div>
          <HowItWorks />
        </div>
      </section>

      <section className="sec sec-ghat" id="languages">
        <div className="wrap"><LanguageDemo /></div>
      </section>

      <section className="sec sec-sand" id="katha">
        <div className="wrap two">
          <div>
            <div className="sec-head" style={{ marginBottom: 24 }}>
              <p className="kicker">Katha</p>
              <h2>A guide that knows the stories, and tells you which are stories.</h2>
              <p>History is told as history. Every legend begins with &quot;As the story goes&quot;, so you always know which is which. Each paragraph carries its source.</p>
            </div>
            {[["City Katha", "A portrait of a whole city in 2, 5 or 10 minutes: what it is, who built it, what it eats."], ["Place Katha", "One temple, fort or palace in depth, with the legends people tell there."], ["Day Katha", "The story of your planned day, stop by stop, ready before you leave the hotel."]].map(([b, s]) => (
              <div className="kt-point" key={b}><b>{b}</b><span>{s}</span></div>
            ))}
          </div>
          <KathaPlayer />
        </div>
      </section>

      <section className="sec sec-night" id="ways">
        <div className="wrap">
          <div className="sec-head">
            <p className="kicker">Getting there</p>
            <h2>Every way to get there, compared honestly.</h2>
            <p>Road, rail and air are routed on a real network and compared door to door, including the time it takes to reach the airport or the station.</p>
          </div>
          <div className="two">
            <div className="routemap">
              <svg viewBox="0 0 880 760" role="img" aria-label="Map of the road, rail and air routes from Bengaluru to Goa">
                <rect width="880" height="760" fill="#1B3A4C" />
                <path d="M120 0 L46 28 L60 62 L82 104 L76 118 L102 144 L124 198 L144 238 L180 268 L184 290 L202 314 L208 344 L230 402 L258 476 L268 532 L288 626 L318 700 L340 760 L880 760 L880 0 Z" fill="#203545" />
                <path d="M838 606 L740 532 L600 354 L504 308 L344 128 L322 108 L282 112 L218 112 L197 115 L150 112 L111 120 L87 100" fill="none" stroke="#E3A33B" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
                <path d="M838 606 L760 520 L690 430 L600 354 L504 308 L344 128 L322 108 L222 108 L183 137 L111 145" fill="none" stroke="#F4EFE6" strokeWidth="4" strokeDasharray="12 9" strokeLinecap="round" />
                <path d="M838 606 Q520 160 93 54" fill="none" stroke="#8FC0DA" strokeWidth="4" strokeDasharray="2 10" strokeLinecap="round" />
                <g fill="#F4EFE6" fontSize="21" fontWeight="600">
                  <circle cx="838" cy="606" r="8" /><circle cx="87" cy="100" r="8" /><circle cx="93" cy="54" r="6" /><circle cx="344" cy="128" r="6" />
                  <text x="760" y="646">Bengaluru</text><text x="102" y="94">Panaji</text><text x="104" y="48">Mopa airport</text><text x="356" y="124">Hubballi</text>
                </g>
              </svg>
              <div className="legend"><span><i />Road</span><span><i className="rail" />Rail</span><span><i className="air" />Air</span></div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="ways-table">
                <thead><tr><th>Way</th><th>Door to door</th><th>One way for 4 (est.)</th><th>What you see</th></tr></thead>
                <tbody>
                  {ways.map(([n, s, d, p, v]) => (
                    <tr key={n}><td><b>{n}</b><small>{s}</small></td><td>{d}</td><td>{p}</td><td>{v}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="fine">Figures here are illustrative. In the product they come from live fares and the rail timetable when you plan.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="sec sec-paper">
        <div className="wrap two">
          <div className="sec-head" style={{ marginBottom: 0 }}>
            <p className="kicker">Plans that hold up</p>
            <h2>Checked before you see it.</h2>
            <p>The AI understands you, compares options and writes the plan up. Before any plan reaches you, our planner tests every stop on every day, and fixes the day that fails.</p>
          </div>
          <div className="inspector">
            <div className="inspector-head"><b>Goa with family, 4 days</b><span className="passed">41 of 41 passed</span></div>
            <table className="check-t">
              <tbody>
                {checks.map(([n, s, r]) => (
                  <tr key={n}><td>{n}<small>{s}</small></td><td>{r}</td><td>Passed</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="sec sec-sand">
        <div className="wrap two" style={{ alignItems: "center" }}>
          <div className="mini-phone" aria-label="A trip planned in a chat">
            <div className="mp-head"><Logo sw={1.8} /><div><b>Travel Yantra</b><small>Replies in your language</small></div></div>
            <div className="mp-body">
              <div className="b-in">Goa jaana hai 11 se 14 Dec, mummy papa aur behen ke saath. Veg khana.</div>
              <div className="b-out">Theek hai. Bengaluru se Goa, 11 se 14 Dec, aap chaar log, ek 60 se upar, veg khana. Kaise jaana pasand karenge?</div>
              <div className="b-btns"><span>Fly to Mopa</span><span>Rail past Dudhsagar</span><span>Road via Hubballi</span></div>
              <div className="b-in">Rail past Dudhsagar</div>
              <div className="b-out">Plan taiyaar hai. Shanivar ko Old Goa ke churches, Mangueshi mandir aur spice farm mein lunch. Poora plan PDF mein bhej raha hoon.</div>
            </div>
          </div>
          <div>
            <div className="sec-head" style={{ marginBottom: 16 }}>
              <p className="kicker">Wherever you are</p>
              <h2>On the web, on WhatsApp, on Telegram.</h2>
            </div>
            {channels.map(([d, b, s]) => (
              <div className="chan-row" key={b}>
                <span className="ic-box"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg></span>
                <div><b>{b}</b><span>{s}</span></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="cta">
        <div className="wrap cta-in">
          <h2>Where are you going next?</h2>
          <div className="cta-box">
            <Link className="cta-field" href="/signin/">Bengaluru to Goa, 11 to 14 Dec, with my parents</Link>
            <Link className="btn btn-cream" href="/signin/">Plan a trip</Link>
          </div>
        </div>
      </section>

      <footer className="foot">
        <div className="wrap">
          <div className="foot-grid">
            <div><Brand accent="#E07A52" /><p>Plans, stories and bookings for travel in India, in six languages.</p></div>
            <div><h4>Product</h4>{links.Product.map(([t, h]) => <Link key={t} href={h}>{t}</Link>)}</div>
            <div><h4>Project</h4><p>A final-year major project, Department of Information Science and Engineering, BMS Institute of Technology and Management, Bengaluru.</p></div>
            <div><h4>Legal</h4>{links.Legal.map(([t, h]) => <Link key={t} href={h}>{t}</Link>)}</div>
          </div>
          <div className="foot-base"><span>Prototype with sample data. Fares, timings and ratings shown are illustrative.</span><span>2026</span></div>
        </div>
      </footer>
    </div>
  );
}
