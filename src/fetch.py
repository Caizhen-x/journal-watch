"""OpenAlex fetcher: pulls new papers per journal ISSN since last fetch."""
import requests
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db

OPENALEX = "https://api.openalex.org/works"
USER_AGENT = "journal-watch/0.1 (mailto:fqqqywzwan@gmail.com)"
DEFAULT_LOOKBACK_DAYS = 30


def _abstract_from_inverted_index(idx: dict | None) -> str | None:
    if not idx:
        return None
    pos = {}
    for word, positions in idx.items():
        for p in positions:
            pos[p] = word
    if not pos:
        return None
    return " ".join(pos[i] for i in sorted(pos))


def fetch_journal(issn: str, journal_code: str, since: str) -> list[dict]:
    """Fetch all works from a journal published on or after `since` (YYYY-MM-DD)."""
    papers = []
    cursor = "*"
    while cursor:
        params = {
            "filter": f"primary_location.source.issn:{issn},from_publication_date:{since}",
            "per-page": 200,
            "cursor": cursor,
            "select": "id,doi,title,abstract_inverted_index,authorships,publication_date,primary_location",
        }
        r = requests.get(OPENALEX, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for w in data["results"]:
            if not w.get("doi") or not w.get("title"):
                continue
            papers.append({
                "doi": w["doi"].replace("https://doi.org/", ""),
                "openalex_id": w["id"],
                "journal_code": journal_code,
                "issn": issn,
                "title": w["title"],
                "abstract": _abstract_from_inverted_index(w.get("abstract_inverted_index")),
                "authors": [
                    a["author"]["display_name"]
                    for a in w.get("authorships", [])
                    if a.get("author", {}).get("display_name")
                ],
                "pub_date": w["publication_date"],
            })
        cursor = data.get("meta", {}).get("next_cursor")
        if not data["results"]:
            break
    return papers


def load_journals() -> list[dict]:
    cfg_path = Path(__file__).parent.parent / "data" / "journals.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    out = []
    for journals in cfg.values():
        out.extend(journals)
    return out


def run(lookback_days: int | None = None):
    db.init()
    journals = load_journals()
    today = datetime.now(timezone.utc).date().isoformat()
    inserted_total = 0
    for j in journals:
        with db.conn() as c:
            last = db.get_last_fetched(c, j["issn"])
        # Always look back at least 60 days so abstracts that arrive late get backfilled via upsert.
        floor = (datetime.now(timezone.utc).date() - timedelta(days=lookback_days or 60)).isoformat()
        since = min(last, floor) if last else floor
        try:
            papers = fetch_journal(j["issn"], j["code"], since)
        except requests.HTTPError as e:
            print(f"  [{j['code']}] HTTP error: {e}")
            continue
        new_count = filled_count = 0
        with db.conn() as c:
            for p in papers:
                result = db.upsert_paper(c, p)
                if result == "inserted":
                    new_count += 1
                elif result == "abstract_filled":
                    filled_count += 1
            db.set_last_fetched(c, j["issn"], today)
        print(f"  [{j['code']}] {new_count} new, {filled_count} abstracts filled (since {since}, {len(papers)} returned)")
        inserted_total += new_count
    print(f"\nTotal new papers: {inserted_total}")
    return inserted_total


if __name__ == "__main__":
    import sys
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(lookback)
