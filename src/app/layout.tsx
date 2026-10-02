import type { Metadata } from "next";

import "./globals.css";
import localFont from "next/font/local";

const openAISans = localFont({
  src: [
    { path: "../../fonts/OpenAISans-Regular.ttf", weight: "400", style: "normal" },
    { path: "../../fonts/OpenAISans-Medium.ttf", weight: "500", style: "normal" },
    { path: "../../fonts/OpenAISans-Semibold.ttf", weight: "600", style: "normal" },
    { path: "../../fonts/OpenAISans-RegularItalic.ttf", weight: "400", style: "italic" },
    { path: "../../fonts/OpenAISans-MediumItalic.ttf", weight: "500", style: "italic" },
    { path: "../../fonts/OpenAISans-SemiboldItalic.ttf", weight: "600", style: "italic" },
  ],
  variable: "--font-local-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "viniścaya | Login",
  description: "Helping those who save lives, save more.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" className={openAISans.variable}><body>{children}</body></html>;
}



