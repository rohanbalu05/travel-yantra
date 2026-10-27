import type { Metadata, Viewport } from "next";
import {
  Anek_Bangla,
  Anek_Devanagari,
  Anek_Kannada,
  Anek_Tamil,
  Anek_Telugu,
  Bricolage_Grotesque,
  Figtree,
  JetBrains_Mono,
} from "next/font/google";
import { LangProvider } from "@/lib/i18n";
import "./ty.css";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", display: "swap" });
const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });
const anekKn = Anek_Kannada({ subsets: ["kannada"], variable: "--font-anek-kn", display: "swap" });
const anekHi = Anek_Devanagari({ subsets: ["devanagari"], variable: "--font-anek-hi", display: "swap" });
const anekTa = Anek_Tamil({ subsets: ["tamil"], variable: "--font-anek-ta", display: "swap" });
const anekTe = Anek_Telugu({ subsets: ["telugu"], variable: "--font-anek-te", display: "swap" });
const anekBn = Anek_Bangla({ subsets: ["bengali"], variable: "--font-anek-bn", display: "swap" });
const fonts = [bricolage, figtree, jetbrains, anekKn, anekHi, anekTa, anekTe, anekBn];

export const metadata: Metadata = {
  title: "Travel Yantra",
  description: "Plans, stories and bookings for travel in India, in six languages.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#13212B" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fonts.map((x) => x.variable).join(" ")}>
      <body>
        <LangProvider>{children}</LangProvider>
      </body>
    </html>
  );
}
