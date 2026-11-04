import { Climb } from "@/components/landing/Climb";
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
        <Climb />
        <Stages />
        <Proof />
        <Stats />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
