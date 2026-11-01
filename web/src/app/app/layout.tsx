import type { Metadata } from "next";
import { Shell } from "@/components/app/Shell";
import { WorkspaceProvider } from "@/lib/workspace";

export const metadata: Metadata = {
  title: "ShadowCost · Fernhill Supplies",
  description: "Discover repeated work, approve agents and watch them earn autonomy in shadow mode.",
};

export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    <WorkspaceProvider>
      <Shell>{children}</Shell>
    </WorkspaceProvider>
  );
}
