export type Screen = {
  slug: string;
  path: string;
  title: string;
  blurb: string;
  group: "Start" | "Plan" | "Trip" | "Katha" | "Help" | "Account";
};

export const SCREENS: Screen[] = [
  { slug: "landing", path: "/", title: "Landing", blurb: "What Travel Yantra does, in one screen.", group: "Start" },
  { slug: "signin", path: "/signin/", title: "Sign in", blurb: "Phone or Google sign-in.", group: "Account" },
  { slug: "legal", path: "/legal/", title: "Legal", blurb: "Terms and privacy.", group: "Account" },
  { slug: "home", path: "/home/", title: "Home", blurb: "Your trips and where to go next.", group: "Start" },
  { slug: "plan-start", path: "/plan/start/", title: "Plan a trip", blurb: "Tell us where, when and who.", group: "Plan" },
  { slug: "plan-thinking", path: "/plan/thinking/", title: "Planning", blurb: "The agents work out your route.", group: "Plan" },
  { slug: "plan-options", path: "/plan/options/", title: "Options", blurb: "Road, rail and air side by side.", group: "Plan" },
  { slug: "itinerary", path: "/plan/itinerary/", title: "Itinerary", blurb: "Day by day plan.", group: "Plan" },
  { slug: "book", path: "/book/", title: "Book", blurb: "Compare sellers and open booking links.", group: "Plan" },
  { slug: "trip-live", path: "/trip/live/", title: "Trip live", blurb: "Today on your trip.", group: "Trip" },
  { slug: "my-trips", path: "/trips/", title: "My trips", blurb: "Upcoming and past trips.", group: "Trip" },
  { slug: "katha-home", path: "/katha/", title: "Katha", blurb: "The story of each place.", group: "Katha" },
  { slug: "katha-city", path: "/katha/city/", title: "Katha: city", blurb: "A city's story.", group: "Katha" },
  { slug: "katha-place", path: "/katha/place/", title: "Katha: place", blurb: "A single place's story.", group: "Katha" },
  { slug: "katha-day", path: "/katha/day/", title: "Katha: day", blurb: "The stories for one day.", group: "Katha" },
  { slug: "ask-guide", path: "/ask/", title: "Ask the guide", blurb: "History, food, culture and emergencies.", group: "Help" },
  { slug: "whatsapp", path: "/whatsapp/", title: "WhatsApp", blurb: "Continue on WhatsApp.", group: "Help" },
  { slug: "voice", path: "/voice/", title: "Voice", blurb: "Talk to your guide.", group: "Help" },
  { slug: "settings", path: "/settings/", title: "Settings", blurb: "Language, privacy and data.", group: "Account" },
  { slug: "edge-cases", path: "/edge-cases/", title: "Edge cases", blurb: "Offline, empty and error states.", group: "Help" },
];

export const TABS = [
  { label: "Home", path: "/home/" },
  { label: "Plan", path: "/plan/start/" },
  { label: "Katha", path: "/katha/" },
  { label: "Ask", path: "/ask/" },
  { label: "Trips", path: "/trips/" },
];
