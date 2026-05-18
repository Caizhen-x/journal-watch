"""Claude Haiku classifier: tag each paper with topic[] + method[] codes + relevance."""
import json
import os
import yaml
from pathlib import Path
from anthropic import Anthropic

from . import db

CLASSIFIER_VERSION = "haiku-4.5-v1"
MODEL = "claude-haiku-4-5-20251001"


def _load_taxonomies() -> dict:
    path = Path(__file__).parent.parent / "data" / "taxonomies.yaml"
    return yaml.safe_load(path.read_text())


def _build_system_prompt(tax: dict) -> str:
    topics = "\n".join(f"  - {t['code']}: {t['label']} — {t['description']}" for t in tax["topics"])
    methods = "\n".join(f"  - {m['code']}: {m['label']}" for m in tax["methods"])
    return f"""You are classifying academic papers from agricultural and environmental economics journals for a research group at HU Berlin focused on agri-food chain management.

For each paper, return JSON with:
- topics: list of applicable topic codes (zero or more)
- methods: list of applicable method codes (zero or more)
- relevance: integer 0-10 of relevance to the agri-food chain management research group (10 = directly central, 0 = unrelated)

Only return JSON. No explanation outside JSON.

Topic codes (use exact codes):
{topics}

Method codes (use exact codes):
{methods}

Rules:
- Tag every method actually used in the paper (often more than one).
- Tag every topic the paper substantively addresses (not just mentions).
- If the paper is purely theoretical with no empirical work, methods can be just [theoretical_model].
- relevance score: weight value chains, agri-food systems, sustainability, smallholder/gender, agtech adoption highly. Pure macro environmental econ unrelated to agriculture scores low.
- If you cannot classify (e.g., no abstract), return empty arrays and relevance 0."""


def _classify_one(client: Anthropic, system: str, title: str, abstract: str | None, journal: str) -> dict:
    user_msg = f"Journal: {journal}\nTitle: {title}\n\nAbstract: {abstract or '(no abstract available)'}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if model wraps them
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def run(limit: int | None = None):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=api_key)
    tax = _load_taxonomies()
    system = _build_system_prompt(tax)
    valid_topics = {t["code"] for t in tax["topics"]}
    valid_methods = {m["code"] for m in tax["methods"]}

    db.init()
    with db.conn() as c:
        papers = db.get_unclassified(c, classifier_version=CLASSIFIER_VERSION, limit=limit)

    print(f"Classifying {len(papers)} papers...")
    classified = 0
    for p in papers:
        try:
            result = _classify_one(client, system, p["title"], p["abstract"], p["journal_code"])
        except Exception as e:
            print(f"  [{p['doi']}] error: {e}")
            continue
        topics = [t for t in result.get("topics", []) if t in valid_topics]
        methods = [m for m in result.get("methods", []) if m in valid_methods]
        relevance = int(result.get("relevance", 0))
        with db.conn() as c:
            db.save_classification(c, p["doi"], topics, methods, relevance, CLASSIFIER_VERSION)
        classified += 1
        if classified % 10 == 0:
            print(f"  ...{classified}/{len(papers)}")
    print(f"Classified {classified} papers")
    return classified


if __name__ == "__main__":
    import sys
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(lim)
