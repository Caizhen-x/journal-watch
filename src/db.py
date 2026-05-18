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
    doi               TEXT NOT NULL,
    subscriber_hash   TEXT NOT NULL,
    sent_at           TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (doi, subscriber_hash)
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


def _migrate_digest_log(c):
    """Old schema stored plaintext emails. New schema stores SHA-256 hashes.
    digest_log has always been empty in production, so we drop and recreate."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(digest_log)").fetchall()]
    if cols and "subscriber" in cols and "subscriber_hash" not in cols:
        c.execute("DROP TABLE digest_log")


def init():
    with conn() as c:
        _migrate_digest_log(c)
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


def get_unclassified(
    c,
    classifier_version: str | None = None,
    limit: int | None = None,
    min_abstract_chars: int = 100,
) -> list[sqlite3.Row]:
    """Return papers needing classification.

    A paper needs classification if either:
    - it has never been classified, OR
    - its existing classification's classifier_version differs from `classifier_version` (if provided).

    Skips papers with abstracts shorter than min_abstract_chars unless older than 30 days.
    """
    version_clause = "cls.doi IS NULL"
    params: tuple = ()
    if classifier_version is not None:
        version_clause = "(cls.doi IS NULL OR cls.classifier_version != ?)"
        params = (classifier_version,)
    sql = f"""SELECT p.* FROM papers p
             LEFT JOIN classifications cls ON cls.doi = p.doi
             WHERE {version_clause}
               AND (length(coalesce(p.abstract, '')) >= {int(min_abstract_chars)}
                    OR julianday('now') - julianday(p.pub_date) > 30)
             ORDER BY p.pub_date DESC"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return list(c.execute(sql, params))


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
