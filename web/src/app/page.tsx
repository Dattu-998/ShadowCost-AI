import { Cta } from "@/components/landing/Cta";
import { Footer } from "@/components/landing/Footer";
import { Hero } from "@/components/landing/Hero";
import { Proof } from "@/components/landing/Proof";
import { Showcase } from "@/components/landing/Showcase";
import { Stages } from "@/components/landing/Stages";
import { Stats } from "@/components/landing/Stats";

export default function Home() {
  return (
    <>
      <Hero />
      <main>
        <Showcase />
        <Stages />
        <Proof />
        <Stats />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
