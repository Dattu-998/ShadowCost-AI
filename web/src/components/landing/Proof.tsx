import Image from "next/image";
import data from "@/data/landing.json";
import { Reveal } from "@/lib/reveal";

/**
 * Large marks on tiles (dealt). There are no customer logos to show and none are invented; the
 * tiles carry what ShadowCost actually reads, by name, with what it found in each. Two tiles hold
 * real pictures of the work it inherits: a merchant's hand-kept ledger and an adding machine.
 */
const s = data.sample;
const tiles = [
  { name: "Invoice sheet", fact: `${s.snapshots} daily copies, ${s.invoices} invoices` },
  { name: "Bank export", fact: `${s.payments} payments, ${Math.round(s.payments_linked * 100)}% linked` },
  { name: "Mailbox", fact: `${s.emails} emails, sorted into templates` },
  { name: "Customer list", fact: `${s.customers} customers, an Excel file` },
  {
    name: "Workflows",
    fact: `${data.discovery.workflows.length} of 3 found, precision ${data.discovery.precision.toFixed(2)}`,
  },
  { name: "Event log", fact: "None needed. Small companies don't have one." },
];

function Tile({ name, fact, delay }: { name: string; fact: string; delay: number }) {
  return (
    <Reveal
      delay={delay}
      className="reveal flex aspect-[3/2] flex-col justify-between bg-[#c4d3ca] p-5 md:p-6"
    >
      <p className="text-lead font-extrabold leading-none tracking-tight">{name}</p>
      <p className="text-body leading-snug">{fact}</p>
    </Reveal>
  );
}

function Picture({
  src,
  alt,
  caption,
  width,
  height,
  position,
  drift = false,
}: {
  src: string;
  alt: string;
  caption: string;
  width: number;
  height: number;
  position: string;
  drift?: boolean;
}) {
  return (
    <Reveal as="figure" className="reveal col-span-2 flex flex-col bg-[#c4d3ca]">
      <div className="relative aspect-[3/1.45] overflow-hidden md:aspect-auto md:flex-1">
        <Image
          src={src}
          alt={alt}
          width={width}
          height={height}
          sizes="(min-width: 768px) 50vw, 100vw"
          className={`absolute inset-0 h-full w-full object-cover ${drift ? "drift" : ""}`}
          style={{ objectPosition: position }}
        />
      </div>
      <figcaption className="p-4 text-small md:px-6">{caption}</figcaption>
    </Reveal>
  );
}

export function Proof() {
  return (
    <section aria-labelledby="proof-title" className="bg-sage px-4 py-24 md:px-7 md:py-32">
      <div className="grid grid-cols-2 gap-1.5 md:grid-cols-4 md:gap-2">
        <Reveal className="reveal col-span-2 flex min-h-[220px] flex-col justify-between bg-olive p-6 text-paper">
          <h2 id="proof-title" className="display text-head">
            The files you already have
          </h2>
          <p className="mt-6 max-w-[46ch] text-body leading-snug">
            {data.company} hands over {s.days} days of ordinary files. ShadowCost reads them from
            their names and headers alone, and finds the work that keeps coming back.
          </p>
        </Reveal>
        <Tile {...tiles[0]} delay={60} />
        <Tile {...tiles[1]} delay={120} />
        <Picture
          src="/archive/pittsboro-merchant-business-ledger.jpg"
          alt="A handwritten 1833 merchant's ledger page listing customers and the goods they bought, one entry under another."
          caption="Pittsboro, September 1833: a merchant's ledger, the same entry written by hand, line after line."
          width={1920}
          height={2881}
          position="50% 22%"
          drift
        />
        <Tile {...tiles[2]} delay={60} />
        <Tile {...tiles[3]} delay={120} />
        <Tile {...tiles[4]} delay={60} />
        <Tile {...tiles[5]} delay={120} />
        <Picture
          src="/archive/remington-adding-machine-model-102.jpg"
          alt="A grey Remington adding machine in front of its original red and cardboard box."
          caption="A Remington adding machine: office repetition, mechanised once before."
          width={1920}
          height={1440}
          position="60% 55%"
        />
      </div>
    </section>
  );
}
