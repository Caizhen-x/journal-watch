"""Subscriber registry: reads a Google Sheet (published as CSV) of form responses."""
import csv
import os
import re
import requests
from dataclasses import dataclass, field
from io import StringIO

# Sheet must be published with sharing "anyone with the link can view".
# CSV export URL: https://docs.google.com/spreadsheets/d/{ID}/export?format=csv

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Subscriber:
    email: str
    name: str
    topics: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    min_relevance: int = 5

    def matches(self, paper_topics: list[str], paper_methods: list[str], paper_relevance: int) -> bool:
        if paper_relevance < self.min_relevance:
            return False
        if self.topics and not (set(self.topics) & set(paper_topics)):
            return False
        if self.methods and not (set(self.methods) & set(paper_methods)):
            return False
        return True


def _split_multiselect(value: str) -> list[str]:
    """Google Forms returns multi-select as comma-separated strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _label_to_code(label: str, valid_codes: list[dict]) -> str | None:
    """Map a human-readable label from the form back to a taxonomy code."""
    for entry in valid_codes:
        if entry["label"].lower() == label.lower() or entry["code"].lower() == label.lower():
            return entry["code"]
    return None


def fetch_subscribers(taxonomies: dict) -> list[Subscriber]:
    """Fetch from the published CSV of the subscriber Google Sheet.

    Expected columns (column names matter, order doesn't):
      - 'Email Address' or 'Email'
      - 'Name' (optional)
      - 'Topics' — comma-separated list of topic labels (or codes)
      - 'Methods' — comma-separated list of method labels (or codes)
      - 'Minimum relevance' (optional, integer 0-10; defaults to 5)
      - 'Unsubscribe' (optional, any non-empty value excludes the row)
    """
    csv_url = os.environ.get("SUBSCRIBERS_CSV_URL")
    if not csv_url:
        return []

    r = requests.get(csv_url, timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(StringIO(r.text))

    topics_tax = taxonomies["topics"]
    methods_tax = taxonomies["methods"]

    # Deduplicate by email — last row wins (Google Forms doesn't dedupe).
    by_email: dict[str, Subscriber] = {}
    for row in reader:
        email = (row.get("Email Address") or row.get("Email") or "").strip().lower()
        if not email or not EMAIL_RE.match(email):
            continue
        if (row.get("Unsubscribe") or "").strip():
            by_email.pop(email, None)
            continue

        topic_labels = _split_multiselect(row.get("Topics", ""))
        method_labels = _split_multiselect(row.get("Methods", ""))
        topics = [c for c in (_label_to_code(l, topics_tax) for l in topic_labels) if c]
        methods = [c for c in (_label_to_code(l, methods_tax) for l in method_labels) if c]

        try:
            min_rel = int(row.get("Minimum relevance") or 5)
        except ValueError:
            min_rel = 5

        by_email[email] = Subscriber(
            email=email,
            name=(row.get("Name") or "").strip(),
            topics=topics,
            methods=methods,
            min_relevance=min_rel,
        )

    return list(by_email.values())
