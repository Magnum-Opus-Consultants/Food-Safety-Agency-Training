import type { Metadata } from "next";
import { IBM_Plex_Mono, Jost } from "next/font/google";
import Providers from "./providers";
import "./globals.css";

// Jost 500 is the design system's display substitution (replace if FSA licenses Century Gothic).
const jost = Jost({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-jost" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "FSA Academy · Training Hub",
  description: "The FSA Academy training department's back office.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-ZA" className={`${jost.variable} ${plexMono.variable}`}>
      <head>
        {/* Font Awesome 6.4, as used by the FSA APS portal. */}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
              integrity="sha512-iecdLmaskl7CVkqkXNQ/ZH/XLlvWZOJyj7Yy7tcenmpD1ypASozpmT/E0iPtmFIB46ZmdtAc9eNBvH0H/ZpiBw=="
              crossOrigin="anonymous" referrerPolicy="no-referrer" />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
