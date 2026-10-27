export type Screen = { slug: string; path: string; title: string; blurb: string };

// Voice is cut (27 Oct), so there is no voice route.
export const SCREENS: Screen[] = [
  { slug: "landing", path: "/", title: "Landing", blurb: "What Travel Yantra does, in one screen." },
  { slug: "signin", path: "/signin/", title: "Sign in", blurb: "Continue with Google." },
  { slug: "legal", path: "/legal/", title: "Legal", blurb: "Terms and privacy." },
  { slug: "home", path: "/home/", title: "Home", blurb: "Your trips and where to go next." },
  { slug: "plan-start", path: "/plan/start/", title: "Plan a trip", blurb: "Tell us where, when and who." },
  { slug: "plan-thinking", path: "/plan/thinking/", title: "Planning", blurb: "The agents work out your route." },
  { slug: "plan-options", path: "/plan/options/", title: "Options", blurb: "Road, rail and air side by side." },
  { slug: "itinerary", path: "/plan/itinerary/", title: "Itinerary", blurb: "Day by day plan." },
  { slug: "book", path: "/book/", title: "Book", blurb: "Compare sellers and open booking links." },
  { slug: "trip-live", path: "/trip/live/", title: "Trip live", blurb: "Today on your trip." },
  { slug: "my-trips", path: "/trips/", title: "My trips", blurb: "Upcoming and past trips." },
  { slug: "katha-home", path: "/katha/", title: "Katha", blurb: "The story of each place." },
  { slug: "katha-city", path: "/katha/city/", title: "Katha: city", blurb: "A city's story." },
  { slug: "katha-place", path: "/katha/place/", title: "Katha: place", blurb: "A single place's story." },
  { slug: "katha-day", path: "/katha/day/", title: "Katha: day", blurb: "The stories for one day." },
  { slug: "ask-guide", path: "/ask/", title: "Ask the guide", blurb: "History, food, culture and emergencies." },
  { slug: "whatsapp", path: "/whatsapp/", title: "WhatsApp", blurb: "Continue on WhatsApp." },
  { slug: "settings", path: "/settings/", title: "Settings", blurb: "Language, privacy and data." },
  { slug: "edge-cases", path: "/edge-cases/", title: "Edge cases", blurb: "Offline, empty and error states." },
];

export const NAV = [
  { label: "Home", path: "/home/" },
  { label: "Plan a trip", path: "/plan/start/" },
  { label: "Katha", path: "/katha/" },
  { label: "My trips", path: "/trips/" },
];
