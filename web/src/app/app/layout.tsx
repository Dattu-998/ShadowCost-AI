import type { Metadata } from "next";
import { AppGate } from "@/components/app/AppGate";
import { SessionProvider } from "@/lib/session";

export const metadata: Metadata = {
  title: "ShadowCost",
  description: "Discover repeated work, approve agents and watch them earn autonomy in shadow mode.",
  robots: { index: false },
};

// The gate holds pages back until the session and workspace load, by design; skip the check
// that every segment renders instantly on navigation.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    <SessionProvider>
      <AppGate>{children}</AppGate>
    </SessionProvider>
  );
}
