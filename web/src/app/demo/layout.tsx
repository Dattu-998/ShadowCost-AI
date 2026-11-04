import type { Metadata } from "next";
import { Shell } from "@/components/app/Shell";
import { DemoWorkspaceProvider } from "@/lib/workspace";

export const metadata: Metadata = {
  title: "ShadowCost demo · Fernhill Supplies",
  description: "Try ShadowCost on a sample company: discover repeated work, approve agents and watch them earn autonomy.",
};

export default function DemoLayout({ children }: LayoutProps<"/demo">) {
  return (
    <DemoWorkspaceProvider>
      <Shell>{children}</Shell>
    </DemoWorkspaceProvider>
  );
}
