import type { Metadata, Viewport } from "next";
import { Anek_Devanagari, Bricolage_Grotesque, Figtree, JetBrains_Mono } from "next/font/google";
import { TabBar, TopBar } from "@/components/Nav";
import "./globals.css";

const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", display: "swap" });
const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });
const anek = Anek_Devanagari({ subsets: ["devanagari"], variable: "--font-anek", display: "swap" });

export const metadata: Metadata = {
  title: "Travel Yantra",
  description: "Your whole-journey AI travel companion for India.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#13212B" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${bricolage.variable} ${figtree.variable} ${jetbrains.variable} ${anek.variable}`}>
      <body>
        <div className="shell">
          <TopBar />
          <main>{children}</main>
          <TabBar />
        </div>
      </body>
    </html>
  );
}
