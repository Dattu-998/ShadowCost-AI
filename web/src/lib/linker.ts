/**
 * A browser port of ShadowCost's case linker (src/shadowcost/ingest/linking.py): resolve a bank
 * line to the invoice it pays, from its reference if it has a usable one, otherwise from the exact
 * amount plus a payer name that resembles the customer. Like the original, it prefers leaving a
 * payment unlinked over linking it to the wrong invoice.
 */

export type Invoice = { id: string; customer: string; amount: number };

export type BankLine = { payer: string; amount: number | null; reference: string };

export type Link =
  | { kind: "reference"; invoice: Invoice; read: string }
  | { kind: "amount+payer"; invoice: Invoice; similarity: number }
  | { kind: "none"; reason: string };

const MENTION = /\b([A-Za-z]{1,8})[\s\-_#/:]?(\d{2,})\b/g;
const SUFFIXES = new Set(["LTD", "LIMITED", "LLC", "INC", "CO", "PLC", "LIMITE"]);
const MIN_SIMILARITY = 0.5;
const MIN_MARGIN = 0.1;

const canonical = (text: string) => text.toUpperCase().replace(/[^A-Z0-9]/g, "");

export function parseBankLine(text: string): BankLine {
  const lines = text.split("\n").map((l) => l.trim());
  const amountMatch = text.match(/\d[\d,]*\.\d{2}\b/);
  const refLine = lines.find((l) => /^ref(erence)?\b/i.test(l)) ?? "";
  const reference = refLine.replace(/^ref(erence)?\s*:?\s*/i, "").replace(/^\(?none\)?$/i, "");
  const payer = lines.find((l) => l && !/\d/.test(l) && !/^ref/i.test(l)) ?? "";
  return {
    payer,
    amount: amountMatch ? Number(amountMatch[0].replace(/,/g, "")) : null,
    reference: reference.trim(),
  };
}

export function linkPayment(line: BankLine, invoices: Invoice[]): Link {
  const byCanonical = new Map(invoices.map((i) => [canonical(i.id), i]));
  const byDigits = new Map<string, Invoice[]>();
  for (const invoice of invoices) {
    const digits = invoice.id.replace(/\D/g, "");
    byDigits.set(digits, [...(byDigits.get(digits) ?? []), invoice]);
  }

  if (line.reference) {
    const direct = byCanonical.get(canonical(line.reference));
    if (direct) return { kind: "reference", invoice: direct, read: line.reference };
    const mentioned = [...line.reference.matchAll(MENTION)]
      .map(([, prefix, digits]) => byCanonical.get(prefix.toUpperCase() + digits))
      .filter((i): i is Invoice => Boolean(i));
    if (new Set(mentioned).size === 1) {
      return { kind: "reference", invoice: mentioned[0], read: line.reference };
    }
    const sameDigits = byDigits.get(line.reference.replace(/\D/g, "")) ?? [];
    if (sameDigits.length === 1) {
      return { kind: "reference", invoice: sameDigits[0], read: line.reference };
    }
  }

  if (line.amount === null) {
    return { kind: "none", reason: "There is no amount to match on, so it is left for the person." };
  }
  const cents = Math.round(line.amount * 100);
  const candidates = invoices
    .filter((i) => Math.round(i.amount * 100) === cents)
    .map((invoice) => ({ invoice, similarity: nameSimilarity(line.payer, invoice.customer) }))
    .sort((a, b) => b.similarity - a.similarity);
  if (candidates.length === 0) {
    return {
      kind: "none",
      reason: `No invoice is for exactly ${money(line.amount)}, so it is left for the person.`,
    };
  }
  const [best, second] = candidates;
  if (best.similarity < MIN_SIMILARITY) {
    return {
      kind: "none",
      reason: `${best.invoice.id} is for ${money(line.amount)}, but "${line.payer || "no name"}" doesn't look like ${best.invoice.customer}, so it is left for the person.`,
    };
  }
  if (second && best.similarity - second.similarity < MIN_MARGIN) {
    return { kind: "none", reason: "Two invoices fit equally well, so it is left for the person." };
  }
  return { kind: "amount+payer", invoice: best.invoice, similarity: best.similarity };
}

/** Company-name similarity ignoring case, punctuation and "Ltd"-style suffixes. */
export function nameSimilarity(a: string, b: string): number {
  return ratio(company(a), company(b));
}

function company(name: string): string {
  return name
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, " ")
    .split(" ")
    .filter((w) => w && !SUFFIXES.has(w))
    .join(" ");
}

/** Ratcliff/Obershelp similarity, as Python's difflib.SequenceMatcher.ratio() computes it. */
function ratio(a: string, b: string): number {
  if (!a.length && !b.length) return 1;
  return (2 * matching(a, b)) / (a.length + b.length);
}

function matching(a: string, b: string): number {
  let best = 0;
  let aStart = 0;
  let bStart = 0;
  for (let i = 0; i < a.length; i++) {
    for (let j = 0; j < b.length; j++) {
      let k = 0;
      while (i + k < a.length && j + k < b.length && a[i + k] === b[j + k]) k++;
      if (k > best) [best, aStart, bStart] = [k, i, j];
    }
  }
  if (best === 0) return 0;
  return (
    best +
    matching(a.slice(0, aStart), b.slice(0, bStart)) +
    matching(a.slice(aStart + best), b.slice(bStart + best))
  );
}

export function money(amount: number): string {
  return amount.toLocaleString("en-US", { style: "currency", currency: "USD" });
}
