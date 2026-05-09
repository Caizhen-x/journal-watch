import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    doi             TEXT PRIMARY KEY,
    openalex_id     TEXT UNIQUE,
    journal_code    TEXT NOT NULL,
    issn            TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors_json    TEXT,
    pub_date        TEXT NOT NULL,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_papers_pub_date ON papers(pub_date);
CREATE INDEX IF NOT EXISTS idx_papers_journal ON papers(journal_code);

CREATE TABLE IF NOT EXISTS classifications (
    doi                TEXT PRIMARY KEY REFERENCES papers(doi),
    topics_json        TEXT NOT NULL,
    methods_json       TEXT NOT NULL,
    relevance          INTEGER NOT NULL,
    classifier_version TEXT NOT NULL,
    classified_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fetch_state (
    issn          TEXT PRIMARY KEY,
    last_fetched  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digest_log (
    doi          TEXT NOT NULL,
    subscriber   TEXT NOT NULL,
    sent_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (doi, subscriber)
);
"""


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def upsert_paper(c, paper: dict) -> str:
    """Insert a paper or update its abstract if previously missing.

    Returns 'inserted', 'abstract_filled', or 'unchanged'.
    """
    existing = c.execute("SELECT abstract FROM papers WHERE doi = ?", (paper["doi"],)).fetchone()
    if existing is None:
        c.execute(
            """INSERT INTO papers
               (doi, openalex_id, journal_code, issn, title, abstract, authors_json, pub_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                paper["doi"],
                paper.get("openalex_id"),
                paper["journal_code"],
                paper["issn"],
                paper["title"],
                paper.get("abstract"),
                json.dumps(paper.get("authors", [])),
                paper["pub_date"],
            ),
        )
        return "inserted"
    if not existing["abstract"] and paper.get("abstract"):
        c.execute("UPDATE papers SET abstract = ? WHERE doi = ?", (paper["abstract"], paper["doi"]))
        return "abstract_filled"
    return "unchanged"


def get_unclassified(c, limit: int | None = None, min_abstract_chars: int = 100) -> list[sqlite3.Row]:
    """Return papers needing classification. Skips papers with abstracts shorter than min_abstract_chars
    unless the paper is older than 30 days (then classify with whatever we have)."""
    sql = f"""SELECT p.* FROM papers p
             LEFT JOIN classifications cls ON cls.doi = p.doi
             WHERE cls.doi IS NULL
               AND (length(coalesce(p.abstract, '')) >= {int(min_abstract_chars)}
                    OR julianday('now') - julianday(p.pub_date) > 30)
             ORDER BY p.pub_date DESC"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return list(c.execute(sql))


def save_classification(c, doi: str, topics: list, methods: list, relevance: int, version: str):
    c.execute(
        """INSERT OR REPLACE INTO classifications
           (doi, topics_json, methods_json, relevance, classifier_version)
           VALUES (?, ?, ?, ?, ?)""",
        (doi, json.dumps(topics), json.dumps(methods), relevance, version),
    )


def get_last_fetched(c, issn: str) -> str | None:
    row = c.execute("SELECT last_fetched FROM fetch_state WHERE issn = ?", (issn,)).fetchone()
    return row["last_fetched"] if row else None


def set_last_fetched(c, issn: str, date_str: str):
    c.execute(
        "INSERT OR REPLACE INTO fetch_state (issn, last_fetched) VALUES (?, ?)",
        (issn, date_str),
    )
