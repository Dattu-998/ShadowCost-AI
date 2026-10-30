"""Link bank payments and emails to the case they are about.

A case is one row of a tracked spreadsheet, such as an invoice. Its key
("INV-1001") is how the other sources refer to it, though rarely cleanly:
customers type "INV 1001" or just "1001" as a payment reference, or leave it
blank. The index resolves those variants and falls back to matching a payment
by amount and payer name.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

# A case id in free text: a letter prefix, an optional separator and digits.
# The prefix is required so dates and amounts are not mistaken for ids.
_MENTION = re.compile(r"\b([A-Za-z]{1,8})[\s\-_#/:]?(\d{2,})\b")
_COMPANY_SUFFIXES = {"LTD", "LIMITED", "LLC", "INC", "CO", "PLC", "LIMITE"}

MIN_NAME_SIMILARITY = 0.5  # an amount-only match also needs a plausible payer name
MIN_NAME_MARGIN = 0.1  # with several same-amount candidates, the best name must stand out


class CaseIndex:
    def __init__(self) -> None:
        self._by_canonical: dict[str, str] = {}
        self._by_digits: dict[str, set[str]] = defaultdict(set)
        self._by_cents: dict[int, set[str]] = defaultdict(set)
        self._names: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._by_canonical)

    def add(self, key: str, amount: float | None = None, name: str = "") -> None:
        self._by_canonical[_canonical(key)] = key
        digits = re.sub(r"\D", "", key)
        if digits:
            self._by_digits[digits].add(key)
        if amount is not None:
            self._by_cents[round(amount * 100)].add(key)
        if name:
            self._names[key] = name

    def mentions(self, text: str) -> list[str]:
        """Case ids written in free text, in order of first appearance."""
        found: list[str] = []
        for prefix, digits in _MENTION.findall(text):
            key = self._by_canonical.get(prefix.upper() + digits)
            if key and key not in found:
                found.append(key)
        return found

    def lookup_reference(self, reference: str) -> str | None:
        """Resolve a reference field such as "INV-1001", "inv 1001" or "1001"."""
        if not reference.strip():
            return None
        key = self._by_canonical.get(_canonical(reference))
        if key:
            return key
        found = self.mentions(reference)
        if len(found) == 1:
            return found[0]
        # A bare number is only trusted when exactly one case has those digits.
        keys = self._by_digits.get(re.sub(r"\D", "", reference), set())
        return next(iter(keys)) if len(keys) == 1 else None

    def match_payment(self, amount: float, payer: str) -> str | None:
        """The case whose amount matches exactly and whose name resembles the payer."""
        candidates = sorted(self._by_cents.get(round(amount * 100), ()))
        scored = sorted(
            ((name_similarity(payer, self._names.get(key, "")), key) for key in candidates),
            reverse=True,
        )
        if not scored:
            return None
        best_score, best_key = scored[0]
        if best_score < MIN_NAME_SIMILARITY:
            return None
        if len(scored) > 1 and best_score - scored[1][0] < MIN_NAME_MARGIN:
            return None
        return best_key

    def link_payment(self, reference: str, amount: float | None, payer: str) -> tuple[str, str]:
        """Return ``(case_id, link_method)``, or ``("", "")`` when nothing matches."""
        key = self.lookup_reference(reference)
        if key:
            return key, "reference"
        if amount is not None:
            key = self.match_payment(amount, payer)
            if key:
                return key, "amount+payer"
        return "", ""


def name_similarity(a: str, b: str) -> float:
    """Similarity of two company names, ignoring case, punctuation and "Ltd"-style suffixes.

    Bank statements upper-case and truncate names, so "DUNE STUDIO LIMITE" should
    still match "Dune Studio Ltd".
    """
    return SequenceMatcher(None, _company(a), _company(b)).ratio()


def _company(name: str) -> str:
    words = re.sub(r"[^A-Z0-9]+", " ", name.upper()).split()
    return " ".join(w for w in words if w not in _COMPANY_SUFFIXES)


def _canonical(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def to_amount(text: str) -> float | None:
    """Parse "$1,318.88", "1318.88" or "-25.00"; ``None`` when it isn't a number."""
    cleaned = re.sub(r"[^\d.\-]", "", str(text))
    try:
        return float(cleaned)
    except ValueError:
        return None
