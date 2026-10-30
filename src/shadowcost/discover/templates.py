"""Group sent emails into templates: the same kind of email, whatever the wording.

Emails are masked first, so that ids, amounts, dates and the recipient's name
don't make two reminders look different. They are then clustered by cosine
distance between TF-IDF vectors of word 1-2 grams, using average-linkage
agglomerative clustering with a distance cut-off, so the number of templates
doesn't have to be known in advance.

Average linkage needs the full pairwise distance matrix, which is fine for a
small company's mailbox (thousands of emails) but would need a different method
for much larger ones.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

# Tuned on synthetic seeds 1, 2 and 11 (never on the committed sample, seed 7):
# 0.75 kept every template pure while merging rephrasings; from 0.8 different
# kinds of email start to merge, so the margin is small.
DEFAULT_DISTANCE = 0.75

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_MASKS = [
    (re.compile(r"\S+@\S+"), " <email> "),
    (re.compile(r"[$£€]\s?\d[\d,]*(\.\d+)?"), " <amount> "),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), " <date> "),
    (re.compile(rf"\b\d{{1,2}} ({_MONTHS})[a-z]* \d{{4}}\b", re.IGNORECASE), " <date> "),
    (re.compile(r"\b[A-Za-z]{1,8}[\s\-_#/:]?\d{2,}\b"), " <id> "),
    (re.compile(r"\b\d+(\.\d+)?\b"), " <num> "),
]
# Parts of an address that say nothing about who the counterparty is.
_GENERIC_ADDRESS_WORDS = {
    "example", "com", "org", "net", "co", "uk", "io", "mail", "email",
    "accounts", "billing", "finance", "admin", "info", "hello", "contact", "team",
}  # fmt: skip


@dataclass(frozen=True)
class Template:
    template_id: str
    label: str  # the most common masked subject line
    size: int
    cohesion: float  # mean cosine similarity of members to the template's centroid


def mask(text: str, counterparty: str = "") -> str:
    """Replace the parts of an email that vary from one instance to the next."""
    for pattern, replacement in _MASKS:
        text = pattern.sub(replacement, text)
    # The recipient's name ("Hi Alder Bakery team") usually echoes their address.
    for word in set(re.split(r"[^a-z0-9]+", counterparty.lower())):
        if len(word) >= 3 and word not in _GENERIC_ADDRESS_WORDS:
            text = re.sub(rf"\b{re.escape(word)}\b", " <party> ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def cluster_templates(
    sent: pd.DataFrame, distance_threshold: float = DEFAULT_DISTANCE
) -> tuple[dict[str, str], list[Template]]:
    """Assign each sent email (an event-table slice) to a template.

    Returns ``{object_id: template_id}`` and the templates, largest first.
    """
    if sent.empty:
        return {}, []
    payloads = sent["payload"].tolist()
    texts = [mask(f"{p['subject']}\n{p['body']}", p.get("to", "")) for p in payloads]
    subjects = [mask(p["subject"], p.get("to", "")) for p in payloads]

    vectors = TfidfVectorizer(
        ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"<?\w+>?"
    ).fit_transform(texts)
    if len(texts) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=distance_threshold,
            metric="cosine",
            linkage="average",
        ).fit_predict(vectors.toarray())

    # Number templates by size, largest first; ties by first appearance.
    order = sorted(
        set(labels), key=lambda c: (-int((labels == c).sum()), int(np.argmax(labels == c)))
    )
    templates, template_of = [], {}
    for rank, cluster in enumerate(order, start=1):
        template_id = f"T{rank:02d}"
        members = np.flatnonzero(labels == cluster)
        centroid = np.asarray(vectors[members].mean(axis=0)).ravel()
        norm = np.linalg.norm(centroid)
        similarity = vectors[members] @ centroid / norm if norm else np.zeros(len(members))
        label = Counter(subjects[i] for i in members).most_common(1)[0][0]
        templates.append(
            Template(template_id, label, len(members), round(float(similarity.mean()), 3))
        )
        for i in members:
            template_of[sent["object_id"].iloc[i]] = template_id
    return template_of, templates
