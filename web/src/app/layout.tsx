import type { Metadata } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

const schibsted = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin"],
  weight: ["400", "600", "800"],
});

export const metadata: Metadata = {
  title: "ShadowCost: agents that earn autonomy",
  description:
    "ShadowCost finds repetitive invoice, payment and email work in a small company, and hands it to an agent only after the agent has matched the person, case by case.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The inline script below adds `js` to <html> before hydration, on purpose.
    <html lang="en" className={schibsted.variable} suppressHydrationWarning>
      <head>
        {/* Lets CSS hide not-yet-revealed sections only when scripts actually run. */}
        <script dangerouslySetInnerHTML={{ __html: "document.documentElement.classList.add('js')" }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
