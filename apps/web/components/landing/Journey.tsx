import Link from "next/link";
import { Logo } from "@/components/Brand";
import { Wave } from "@/components/Wave";

// The landing hero from design/prototype/Main.dc.html: one pinned stage, driven
// by scroll (CSS scroll-driven animations, no JS). Browsers without
// animation-timeline, and anyone who asks for reduced motion, get the hero and
// the four chapters as still cards (landing.css, .ride-still).

const CHAPTERS: { k: string; h: string; p: string; icon: string }[] = [
  {
    k: "One way to go",
    h: "By road",
    p: "Bengaluru to Panaji is about 560 km. The plan puts lunch at Hubballi and gets you down the ghat before dark.",
    icon: "M5 16V12l2-5h10l2 5v4M3 16h18v2H3zM6.5 12h11",
  },
  {
    k: "Another way",
    h: "By air",
    p: "About seventy minutes to Mopa. Fares from the sellers side by side, with the drive to the airport and the cab after landing counted in.",
    icon: "M3 13h13.5a3.5 3.5 0 0 0 0-3H13L10 5H8l1.5 5H5L3.5 8H2l1 5ZM9 13l-1.5 5h2L13 13",
  },
  {
    k: "The scenic one",
    h: "By rail",
    p: "The line from Londa runs right past Dudhsagar falls. Trains, classes and timings come from the timetable, with the IRCTC details ready to copy.",
    icon: "M8 3h8a2 2 0 0 1 2 2v11H6V5a2 2 0 0 1 2-2ZM6 10h12M8 16l-2 4M16 16l2 4M7 19h10",
  },
  {
    k: "When you arrive",
    h: "Then, the story",
    p: "Every place comes with a Katha: its history, its legends and the food worth trying, in your language, labelled so you know which is which.",
    icon: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5ZM4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5",
  },
];

const Ic = ({ d }: { d: string }) => (
  <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={d} /></svg>
);

function World() {
  return (
    <div className="world" aria-hidden="true">
      <div className="ch ch-car">
        <div className="sky-car" />
        <svg className="hills hills-far" viewBox="0 0 1600 200" preserveAspectRatio="none"><path d="M0 200 L0 118 C120 92 210 58 330 78 C450 98 530 40 670 50 C810 60 870 108 990 100 C1110 92 1190 30 1330 46 C1450 60 1520 98 1600 92 L1600 200 Z" fill="#8EA398" /></svg>
        <svg className="hills hills-mid" viewBox="0 0 1600 200" preserveAspectRatio="none"><path d="M0 200 L0 120 C150 96 260 132 380 110 C520 86 600 136 760 122 C900 110 980 74 1120 96 C1260 118 1380 98 1600 112 L1600 200 Z" fill="#5F7D6C" /><path d="M280 116 l14 -40 l14 40 Z M330 112 l10 -28 l10 28 Z M1180 100 l14 -42 l14 42 Z M1236 104 l10 -30 l10 30 Z M640 128 l12 -34 l12 34 Z" fill="#4A6656" /></svg>
        <div className="roadwrap"><div className="road" /></div>
        <div className="sign"><div className="sign-board"><span>Dharwad</span><b>18 km</b><span>Panaji</span><b>186 km</b></div><div className="sign-post"><i /><i /></div></div>
        <svg className="full frame-car" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
          <path fill="#10171C" fillRule="evenodd" d="M0 0H1600V900H0Z M170 92 Q800 52 1430 92 L1540 650 Q800 708 60 650 Z" />
          <path d="M60 650 Q800 708 1540 650" fill="none" stroke="#28333B" strokeWidth="6" />
          <rect x="790" y="58" width="20" height="34" fill="#1A242B" />
          <rect x="712" y="88" width="176" height="54" rx="10" fill="#1A242B" />
          <rect x="722" y="97" width="156" height="36" rx="6" fill="#33434E" />
          <circle cx="1240" cy="960" r="250" fill="none" stroke="#0A0F12" strokeWidth="54" />
          <rect x="300" y="700" width="196" height="114" rx="12" fill="#0B1014" />
          <rect x="310" y="710" width="176" height="94" rx="6" fill="#1D2B35" />
          <text x="326" y="740" fill="#9FB6C4" fontFamily="Figtree, sans-serif" fontSize="15">Next stop</text>
          <text x="326" y="769" fill="#F4EFE6" fontFamily="Figtree, sans-serif" fontSize="20" fontWeight="700">Lunch, Hubballi</text>
          <text x="326" y="793" fill="#E3A33B" fontFamily="Figtree, sans-serif" fontSize="15">42 km, 12:40</text>
        </svg>
      </div>

      <div className="ch ch-plane">
        <div className="sky-plane" />
        <svg className="coast" viewBox="0 0 2400 400" preserveAspectRatio="none">
          <rect width="2400" height="400" fill="#4A84A3" />
          <path d="M0 400 L0 250 C200 230 300 300 520 270 C700 246 820 180 1000 200 C1180 220 1260 300 1480 280 C1700 260 1820 190 2020 210 C2200 228 2300 260 2400 250 L2400 400 Z" fill="#C9B48A" />
          <path d="M0 400 L0 284 C220 266 320 334 540 304 C720 280 840 218 1020 236 C1200 256 1280 334 1500 314 C1720 294 1840 226 2040 244 C2210 260 2310 292 2400 284 L2400 400 Z" fill="#6E8A5C" />
          <path d="M0 252 C200 232 300 302 520 272 C700 248 820 182 1000 202 C1180 222 1260 302 1480 282 C1700 262 1820 192 2020 212 C2200 230 2300 262 2400 252" fill="none" stroke="#EEF0E6" strokeWidth="4" opacity=".8" />
          <path d="M600 330 C700 320 760 360 860 352 M1600 320 C1680 312 1760 346 1860 340" fill="none" stroke="#4A84A3" strokeWidth="10" />
        </svg>
        <svg className="clouds clouds-far" viewBox="0 0 3200 300" preserveAspectRatio="none">
          <g fill="#F2F5F5"><ellipse cx="220" cy="170" rx="120" ry="34" /><ellipse cx="290" cy="150" rx="80" ry="40" /><ellipse cx="900" cy="120" rx="150" ry="36" /><ellipse cx="980" cy="98" rx="90" ry="42" /><ellipse cx="1600" cy="190" rx="130" ry="30" /><ellipse cx="1660" cy="170" rx="70" ry="34" /><ellipse cx="2300" cy="130" rx="160" ry="38" /><ellipse cx="2380" cy="110" rx="90" ry="40" /><ellipse cx="2950" cy="180" rx="120" ry="30" /></g>
        </svg>
        <svg className="clouds clouds-near" viewBox="0 0 3200 400" preserveAspectRatio="none">
          <g fill="#FBFCFB"><ellipse cx="420" cy="250" rx="260" ry="70" /><ellipse cx="540" cy="200" rx="160" ry="90" /><ellipse cx="320" cy="220" rx="130" ry="70" /><ellipse cx="1400" cy="280" rx="300" ry="60" /><ellipse cx="1520" cy="236" rx="170" ry="80" /><ellipse cx="2400" cy="230" rx="280" ry="74" /><ellipse cx="2280" cy="196" rx="150" ry="82" /><ellipse cx="2540" cy="214" rx="120" ry="60" /></g>
        </svg>
        <svg className="full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
          <path d="M-40 900 L-40 704 L760 812 L830 900 Z" fill="#C3C9CE" />
          <path d="M-40 704 L760 812" stroke="#99A2AA" strokeWidth="10" />
          <path d="M720 806 L800 716 L822 728 L772 814 Z" fill="#A9B1B8" />
        </svg>
        <svg className="full frame-plane" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
          <path fill="#E4DFD5" fillRule="evenodd" d="M0 0H1600V900H0Z M680 110H920A260 260 0 0 1 1180 370V530A260 260 0 0 1 920 790H680A260 260 0 0 1 420 530V370A260 260 0 0 1 680 110Z" />
          <path fill="none" stroke="#CFC8BA" strokeWidth="24" d="M676 86H924A284 284 0 0 1 1208 370V530A284 284 0 0 1 924 814H676A284 284 0 0 1 392 530V370A284 284 0 0 1 676 86Z" />
          <path fill="none" stroke="#B9B1A2" strokeWidth="3" d="M680 110H920A260 260 0 0 1 1180 370V530A260 260 0 0 1 920 790H680A260 260 0 0 1 420 530V370A260 260 0 0 1 680 110Z" />
        </svg>
      </div>

      <div className="ch ch-train">
        <div className="sky-train" />
        <svg className="ridge ridge-far" viewBox="0 0 2400 300" preserveAspectRatio="none"><path d="M0 300 L0 150 C180 90 320 120 480 70 C640 20 780 90 960 60 C1140 30 1260 110 1440 80 C1620 50 1760 120 1940 70 C2120 20 2260 90 2400 70 L2400 300 Z" fill="#7C9A84" /></svg>
        <svg className="ridge ridge-mid" viewBox="0 0 2400 300" preserveAspectRatio="none"><path d="M0 300 L0 170 C160 130 300 170 460 130 C620 90 760 150 940 120 C1120 90 1240 160 1420 130 C1600 100 1740 170 1920 130 C2100 90 2240 150 2400 130 L2400 300 Z" fill="#567A5E" /></svg>
        <svg className="falls" viewBox="0 0 600 700" preserveAspectRatio="xMidYMax meet">
          <path d="M0 700 L0 180 C60 150 120 120 190 130 C260 140 320 90 400 110 C470 128 540 160 600 150 L600 700 Z" fill="#3F4C40" />
          <path d="M0 190 C70 150 130 128 190 138 C260 150 320 100 400 120 C470 138 540 168 600 158 L600 214 C520 224 470 192 400 182 C320 170 260 202 190 198 C120 194 70 216 0 238 Z" fill="#4E7A54" />
          <g className="flow" fill="none" stroke="#F6F5EE" strokeLinecap="round">
            <path d="M262 150 C258 300 250 450 240 690" strokeWidth="22" />
            <path d="M300 140 C298 300 296 470 300 690" strokeWidth="30" />
            <path d="M338 150 C344 300 352 470 362 690" strokeWidth="20" />
            <path d="M226 200 C220 360 214 520 206 690" strokeWidth="10" opacity=".8" />
            <path d="M372 190 C382 350 392 520 404 690" strokeWidth="10" opacity=".8" />
          </g>
          <ellipse cx="300" cy="684" rx="230" ry="46" fill="#F3F4EE" opacity=".55" />
        </svg>
        <svg className="bush" viewBox="0 0 3200 300" preserveAspectRatio="none"><path d="M0 300 L0 120 C60 60 140 80 190 120 C240 60 330 70 380 120 C430 50 520 60 580 118 C640 70 720 76 780 120 C830 60 920 66 980 120 C1040 50 1120 64 1180 116 C1240 70 1320 80 1380 120 C1440 56 1520 66 1600 120 C1660 60 1740 80 1790 120 C1840 60 1930 70 1980 120 C2030 50 2120 60 2180 118 C2240 70 2320 76 2380 120 C2430 60 2520 66 2580 120 C2640 50 2720 64 2780 116 C2840 70 2920 80 2980 120 C3040 56 3120 66 3200 120 L3200 300 Z" fill="#2F4B36" /></svg>
        <div className="poles" />
        <svg className="full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
          <path fill="#58747F" fillRule="evenodd" d="M0 0H1600V900H0Z M330 130H1270Q1300 130 1300 160V690Q1300 720 1270 720H330Q300 720 300 690V160Q300 130 330 130Z" />
          <path d="M300 130H1300V720H300Z" fill="none" stroke="#3F5966" strokeWidth="16" />
          <g fill="#8E9FA6"><rect x="300" y="380" width="1000" height="15" /><rect x="300" y="470" width="1000" height="15" /><rect x="300" y="560" width="1000" height="15" /><rect x="300" y="650" width="1000" height="15" /></g>
          <g fill="#C9D3D7"><rect x="300" y="380" width="1000" height="4" /><rect x="300" y="470" width="1000" height="4" /><rect x="300" y="560" width="1000" height="4" /><rect x="300" y="650" width="1000" height="4" /></g>
          <rect x="260" y="720" width="1080" height="54" fill="#46606C" />
          <rect x="0" y="806" width="1600" height="94" fill="#2C4C78" />
          <path d="M0 818H1600" stroke="#244066" strokeWidth="4" />
          <path d="M1180 664 L1236 664 L1229 720 L1187 720 Z" fill="#EDE8DA" opacity=".6" />
          <path d="M1184 680 L1232 680 L1228 717 L1188 717 Z" fill="#A86B34" />
          <path className="steam" d="M1200 652 C1192 632 1208 618 1200 598" stroke="#F2F2EC" strokeWidth="3" fill="none" />
          <path className="steam steam2" d="M1216 652 C1224 632 1208 618 1216 598" stroke="#F2F2EC" strokeWidth="3" fill="none" />
        </svg>
      </div>

      <div className="ch ch-goa">
        <div className="sky-goa" />
        <svg className="full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
          <circle className="sun" cx="1120" cy="450" r="62" fill="#F8E3B2" />
          <rect y="540" width="1600" height="160" fill="#3B7A91" />
          <g className="glint" stroke="#F4D7A0" strokeWidth="5" strokeLinecap="round"><path d="M1060 572H1180" /><path d="M1080 600H1160" /><path d="M1095 628H1145" /><path d="M1106 654H1134" /></g>
          <path d="M0 690 C300 668 600 700 900 684 C1200 668 1400 692 1600 680 V900 H0Z" fill="#E2C898" />
          <g fill="#9E4529">
            <rect x="250" y="520" width="460" height="176" />
            <rect x="285" y="410" width="390" height="112" />
            <rect x="340" y="318" width="280" height="94" />
            <path d="M376 320 L376 272 Q480 196 584 272 L584 320 Z" />
            <rect x="474" y="176" width="12" height="44" /><rect x="462" y="188" width="36" height="10" />
          </g>
          <g fill="#B85B37">
            <rect x="270" y="520" width="10" height="176" /><rect x="680" y="520" width="10" height="176" /><rect x="402" y="520" width="8" height="176" /><rect x="550" y="520" width="8" height="176" />
            <rect x="305" y="410" width="8" height="112" /><rect x="647" y="410" width="8" height="112" />
            <rect x="250" y="512" width="460" height="10" /><rect x="285" y="402" width="390" height="10" />
          </g>
          <g fill="#6D2E1B">
            <path d="M452 696 V626 A28 28 0 0 1 508 626 V696 Z" />
            <path d="M318 696 V640 A18 18 0 0 1 354 640 V696 Z" />
            <path d="M606 696 V640 A18 18 0 0 1 642 640 V696 Z" />
            <path d="M466 500 V462 A14 14 0 0 1 494 462 V500 Z" />
            <path d="M350 500 V470 A12 12 0 0 1 374 470 V500 Z" />
            <path d="M586 500 V470 A12 12 0 0 1 610 470 V500 Z" />
            <circle cx="480" cy="364" r="20" />
            <circle cx="480" cy="282" r="18" />
          </g>
          <g fill="none" stroke="#21342A" strokeLinecap="round">
            <path d="M1350 900 C1356 770 1384 650 1444 548" strokeWidth="16" />
            <path d="M1444 548 C1384 506 1324 512 1270 546" strokeWidth="12" />
            <path d="M1444 548 C1414 476 1372 446 1318 436" strokeWidth="12" />
            <path d="M1444 548 C1482 474 1534 452 1594 462" strokeWidth="12" />
            <path d="M1444 548 C1504 526 1562 546 1604 588" strokeWidth="12" />
            <path d="M1444 548 C1452 604 1442 644 1418 684" strokeWidth="10" />
            <path d="M1530 900 C1532 806 1548 726 1580 654" strokeWidth="12" />
            <path d="M1580 654 C1540 626 1500 630 1466 652" strokeWidth="9" />
            <path d="M1580 654 C1566 606 1538 588 1504 582" strokeWidth="9" />
            <path d="M1580 654 C1610 608 1640 598 1680 604" strokeWidth="9" />
          </g>
        </svg>
        <div className="katha-card">
          <div className="kc-head"><b>Old Goa in 2 minutes</b><span>Katha</span></div>
          <div className="kc-langs"><span className="on">English</span><span className="kn">ಕನ್ನಡ</span><span className="hi">हिन्दी</span><span className="ta">தமிழ்</span><span className="te">తెలుగు</span><span className="bn">বাংলা</span></div>
          <Wave play />
          <p><span className="tag tag-legend">Legend</span> As the story goes, Parashurama shot an arrow into the sea, the waves drew back, and the Konkan coast rose from the water.</p>
          <p><span className="tag tag-history">History</span> The Basilica of Bom Jesus, consecrated in 1605, keeps the remains of St Francis Xavier.</p>
        </div>
      </div>
    </div>
  );
}

function Phone() {
  return (
    <div className="phone" aria-hidden="true">
      <div className="screen screen-start">
        <div className="ps-top"><Logo sw={1.8} /><span>Travel Yantra</span></div>
        <div className="ps-body">
          <div className="ps-user">Bengaluru to Goa, 11 to 14 Dec. Me, my parents and my sister. Churches, temples, a little beach. Veg food.</div>
          <div className="ps-ai"><b>Three ways to go</b>
            <div className="ps-row"><span>Fly to Mopa</span><span>1 h 10 m</span></div>
            <div className="ps-row"><span>Rail past Dudhsagar</span><span>overnight</span></div>
            <div className="ps-row"><span>Road via Hubballi</span><span>10 h</span></div>
          </div>
          <div className="ps-ai">A Katha for every stop, in your language.</div>
        </div>
        <div className="ps-compose"><span>Ask or change anything</span><Ic d="M9 3h6v11H9zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></div>
      </div>
      <div className="screen screen-end">
        <div className="ps-top"><Logo sw={1.8} /><span>Goa with family</span></div>
        <div className="ps-body">
          <div className="ps-day"><b>Fri</b><span>Fontainhas walk, Miramar sunset</span></div>
          <div className="ps-day"><b>Sat</b><span>Old Goa churches, Mangueshi, spice farm lunch</span></div>
          <div className="ps-day"><b>Sun</b><span>Reis Magos, Aguada, Candolim beach</span></div>
          <div className="ps-day"><b>Mon</b><span>Divar island ferry, train home</span></div>
          <div className="ps-status">Every stop checked</div>
        </div>
        <div className="ps-actions"><span className="ps-btn">Book</span><span className="ps-btn ghost">Play Katha</span></div>
      </div>
      <div className="punch" />
    </div>
  );
}

export function Journey() {
  return (
    <section className="journey" aria-label="A ride from Bengaluru to Goa">
      <div className="stage">
        <svg className="contours" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <g fill="none" stroke="#1C3443" strokeWidth="1.4">
            <path d="M-40 760 C180 700 360 780 600 740 S1000 650 1240 700 S1560 780 1680 730" />
            <path d="M-40 820 C200 770 380 850 620 810 S1020 730 1260 770 S1560 840 1680 800" />
            <path d="M-40 690 C160 640 340 700 580 670 S980 580 1220 630 S1540 700 1680 660" />
            <path d="M1030 300 C1090 220 1260 200 1340 260 C1420 320 1400 430 1300 470 C1200 510 1060 480 1020 400 C1000 360 1005 330 1030 300 Z" />
            <path d="M1070 312 C1120 256 1240 244 1300 290 C1360 336 1346 414 1272 444 C1198 474 1094 452 1066 394 C1050 360 1052 334 1070 312 Z" />
            <path d="M1112 326 C1150 290 1222 286 1262 316 C1300 346 1292 396 1246 414 C1200 432 1132 418 1112 382 C1100 360 1100 342 1112 326 Z" />
            <path d="M120 180 C200 120 340 130 380 200 C420 270 340 330 240 320 C140 310 70 240 120 180 Z" />
            <path d="M160 196 C220 156 316 164 342 214 C368 264 310 300 240 294 C170 288 128 236 160 196 Z" />
          </g>
        </svg>

        <World />

        <div className="hero-copy">
          <div className="hero-in">
            <p className="hc-kicker">Plans, stories and bookings for travel in India</p>
            <h1 className="hc-title">The whole trip, in your language.</h1>
            <p className="hc-sub">Tell Travel Yantra where you want to go, in Kannada, Hindi, Tamil, Telugu, Bengali or English. It works out the route by road, rail or air, checks every stop, tells you the story of each place and lines up every booking.</p>
            <div className="hc-actions">
              <Link className="btn btn-primary" href="/signin/">Plan a trip</Link>
              <Link className="btn btn-on-dark" href="/katha/city/">Hear a Katha</Link>
            </div>
            <p className="hc-hint"><i />Scroll to ride along from Bengaluru to Goa</p>
          </div>
        </div>

        <Phone />

        <div className="rail" aria-hidden="true">
          <div className="rail-labels"><span>Bengaluru</span><span>Road</span><span>Air</span><span>Rail</span><span>Goa</span></div>
          <div className="rail-track"><div className="rail-fill" /></div>
        </div>

        {CHAPTERS.map((c, i) => (
          <div className={`cap cap${i + 1}`} key={c.h} aria-hidden="true">
            <div className="cap-k"><Ic d={c.icon} />{c.k}</div>
            <h3>{c.h}</h3>
            <p>{c.p}</p>
          </div>
        ))}

        <div className="end-copy">
          <div className="end-in">
            <h2>Every way there. Every story on the way.</h2>
            <p>Plan it in words, change it by asking, book it with the official sellers, and travel with a guide that speaks your language.</p>
            <div className="hc-actions">
              <Link className="btn btn-primary" href="/signin/" tabIndex={-1}>Start planning</Link>
              <a className="btn btn-on-dark" href="#how" tabIndex={-1}>See how it works</a>
            </div>
          </div>
        </div>
      </div>

      {/* The same four chapters as still cards: shown instead of the ride when
          the browser can't drive it or the visitor prefers reduced motion, and
          read by screen readers either way. */}
      <ol className="ride-still wrap">
        {CHAPTERS.map((c) => (
          <li key={c.h}>
            <div className="cap-k"><Ic d={c.icon} />{c.k}</div>
            <h3>{c.h}</h3>
            <p>{c.p}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
