import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"
TAXONOMIES_PATH = Path(__file__).parent.parent / "data" / "taxonomies.yaml"


def current_taxonomy_hash() -> str:
    """16-hex-char prefix of SHA-256 over taxonomies.yaml. Used to detect when
    the taxonomy has changed so previously-classified papers are reclassified."""
    return hashlib.sha256(TAXONOMIES_PATH.read_bytes()).hexdigest()[:16]

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
    doi                    TEXT PRIMARY KEY REFERENCES papers(doi),
    topics_json            TEXT NOT NULL,
    methods_json           TEXT NOT NULL,
    relevance              INTEGER NOT NULL,
    classifier_version     TEXT NOT NULL,
    classification_status  TEXT NOT NULL DEFAULT 'ok',   -- 'ok' | 'no_abstract' | 'error'
    taxonomy_hash          TEXT,                          -- prefix of taxonomies.yaml hash at classify time
    classified_at          TEXT NOT NULL DEFAULT (datetime('now'))
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
    """Old schema stored plaintext emails. New schema stores HMAC-SHA256 hashes
    keyed by DIGEST_LOG_HASH_KEY (see src/digest.py). digest_log has always been
    empty in production, so we drop and recreate."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(digest_log)").fetchall()]
    if cols and "subscriber" in cols and "subscriber_hash" not in cols:
        c.execute("DROP TABLE digest_log")


def _migrate_classifications(c):
    """Add classification_status and taxonomy_hash columns if missing.
    Backfills existing rows so the next classifier run doesn't reclassify them all."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(classifications)").fetchall()]
    if not cols:
        return  # Table doesn't exist yet; SCHEMA will create it with the new columns.

    if "classification_status" not in cols:
        c.execute("ALTER TABLE classifications ADD COLUMN classification_status TEXT")
        # Rows whose paper has no usable abstract → 'no_abstract' (don't waste LLM on them).
        c.execute(
            """UPDATE classifications SET classification_status = 'no_abstract'
               WHERE doi IN (SELECT doi FROM papers
                             WHERE length(coalesce(abstract, '')) < 100)"""
        )
        c.execute(
            "UPDATE classifications SET classification_status = 'ok' WHERE classification_status IS NULL"
        )

    if "taxonomy_hash" not in cols:
        c.execute("ALTER TABLE classifications ADD COLUMN taxonomy_hash TEXT")
        # Backfill with current hash so existing rows are considered up-to-date.
        c.execute(
            "UPDATE classifications SET taxonomy_hash = ? WHERE taxonomy_hash IS NULL",
            (current_taxonomy_hash(),),
        )


def init():
    with conn() as c:
        _migrate_digest_log(c)
        _migrate_classifications(c)
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
        # An earlier classify run may have stamped this paper as 'no_abstract' once it
        # crossed the 30-day fallback. Now that an abstract exists, clear that stale
        # decision so the next classify run re-runs the LLM on real content.
        c.execute(
            "DELETE FROM classifications WHERE doi = ? AND classification_status = 'no_abstract'",
            (paper["doi"],),
        )
        return "abstract_filled"
    return "unchanged"


def get_unclassified(
    c,
    classifier_version: str | None = None,
    taxonomy_hash: str | None = None,
    limit: int | None = None,
    min_abstract_chars: int = 100,
) -> list[sqlite3.Row]:
    """Return papers needing (re)classification.

    A paper is returned if any of:
      - never classified, AND (has abstract OR > 30 days old)
      - previously errored (status='error') — retry
      - previously 'ok' but classifier_version differs from `classifier_version`
      - previously 'ok' but taxonomy_hash differs from `taxonomy_hash`

    Rows with status='no_abstract' are NEVER returned by version/taxonomy bumps —
    they're stale only when an abstract appears later, which upsert_paper handles
    by deleting the stale row.
    """
    stale_conds: list[str] = []
    params: list = []
    if classifier_version is not None:
        stale_conds.append("cls.classifier_version != ?")
        params.append(classifier_version)
    if taxonomy_hash is not None:
        stale_conds.append("cls.taxonomy_hash != ?")
        params.append(taxonomy_hash)
    stale_clause = " OR ".join(stale_conds) if stale_conds else "0"

    sql = f"""
        SELECT p.* FROM papers p
        LEFT JOIN classifications cls ON cls.doi = p.doi
        WHERE
            (cls.doi IS NULL
             AND (length(coalesce(p.abstract, '')) >= {int(min_abstract_chars)}
                  OR julianday('now') - julianday(p.pub_date) > 30))
         OR cls.classification_status = 'error'
         OR (cls.classification_status = 'ok' AND ({stale_clause}))
        ORDER BY p.pub_date DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    return list(c.execute(sql, params))


def save_classification(
    c,
    doi: str,
    topics: list,
    methods: list,
    relevance: int,
    version: str,
    status: str = "ok",
    tax_hash: str | None = None,
):
    c.execute(
        """INSERT OR REPLACE INTO classifications
           (doi, topics_json, methods_json, relevance,
            classifier_version, classification_status, taxonomy_hash, classified_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            doi,
            json.dumps(topics),
            json.dumps(methods),
            relevance,
            version,
            status,
            tax_hash,
        ),
    )


def get_last_fetched(c, issn: str) -> str | None:
    row = c.execute("SELECT last_fetched FROM fetch_state WHERE issn = ?", (issn,)).fetchone()
    return row["last_fetched"] if row else None


def set_last_fetched(c, issn: str, date_str: str):
    c.execute(
        "INSERT OR REPLACE INTO fetch_state (issn, last_fetched) VALUES (?, ?)",
        (issn, date_str),
    )
