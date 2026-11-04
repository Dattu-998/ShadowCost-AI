import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";

export const metadata: Metadata = {
  title: "ShadowCost",
  robots: { index: false },
};

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
