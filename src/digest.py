"""Weekly digest builder: match papers → subscribers, generate briefs, send via Gmail SMTP."""
import hashlib
import json
import os
import smtplib
import ssl
import yaml
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path


def _email_hash(email: str) -> str:
    """SHA-256 hex digest of a normalized email. The committed digest_log stores
    only this hash, never the plaintext email, so the public repo cannot leak
    subscriber addresses if the digest is enabled in the future."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()

from anthropic import Anthropic

from . import db
from .classify import MODEL as HAIKU_MODEL
from .subscribers import Subscriber, fetch_subscribers

MAX_PAPERS_PER_DIGEST = 8
LOOKBACK_DAYS = 14  # Consider papers from the last 2 weeks for the weekly digest


def _load_taxonomies() -> dict:
    return yaml.safe_load((Path(__file__).parent.parent / "data" / "taxonomies.yaml").read_text())


def _label_for(code: str, items: list[dict]) -> str:
    for item in items:
        if item["code"] == code:
            return item["label"]
    return code


def _candidate_papers(c, lookback_days: int) -> list[dict]:
    """Recently classified papers, joined with their classifications."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=lookback_days)).isoformat()
    rows = c.execute(
        """SELECT p.doi, p.title, p.abstract, p.authors_json, p.journal_code, p.pub_date,
                  cls.topics_json, cls.methods_json, cls.relevance
           FROM papers p
           JOIN classifications cls ON cls.doi = p.doi
           WHERE p.pub_date >= ?
           ORDER BY cls.relevance DESC, p.pub_date DESC""",
        (cutoff,),
    ).fetchall()
    return [
        {
            "doi": r["doi"],
            "title": r["title"],
            "abstract": r["abstract"],
            "authors": json.loads(r["authors_json"] or "[]"),
            "journal_code": r["journal_code"],
            "pub_date": r["pub_date"],
            "topics": json.loads(r["topics_json"]),
            "methods": json.loads(r["methods_json"]),
            "relevance": r["relevance"],
        }
        for r in rows
    ]


def _already_sent(c, doi: str, email: str) -> bool:
    return bool(
        c.execute(
            "SELECT 1 FROM digest_log WHERE doi = ? AND subscriber_hash = ?",
            (doi, _email_hash(email)),
        ).fetchone()
    )


def _generate_brief(client: Anthropic, paper: dict) -> str:
    if not paper.get("abstract"):
        return "(No abstract available — see paper for details.)"
    prompt = f"""Write a research brief (~180-220 words) for this paper. Cover:
1. Research question
2. Data / setting
3. Method
4. Headline finding
5. Why it matters for agri-food chain management research

Be specific and technical. No preamble like 'This paper...'. Plain prose, no bullets, no headings.

Title: {paper['title']}
Journal: {paper['journal_code']}
Authors: {', '.join(paper['authors'][:5])}
Abstract: {paper['abstract']}"""

    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _render_paper_html(paper: dict, brief: str, taxonomies: dict) -> str:
    topic_labels = [_label_for(t, taxonomies["topics"]) for t in paper["topics"]]
    method_labels = [_label_for(m, taxonomies["methods"]) for m in paper["methods"]]
    authors = ", ".join(paper["authors"][:5])
    if len(paper["authors"]) > 5:
        authors += " et al."
    return f"""
    <div style="margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid #ddd;">
      <h3 style="margin:0 0 8px 0;font-size:17px;">
        <a href="https://doi.org/{escape(paper['doi'])}" style="color:#1a4d8c;text-decoration:none;">{escape(paper['title'])}</a>
      </h3>
      <div style="color:#666;font-size:13px;margin-bottom:6px;">
        {escape(authors)} &middot; <i>{escape(paper['journal_code'])}</i> &middot; {escape(paper['pub_date'])} &middot; relevance {paper['relevance']}/10
      </div>
      <div style="color:#666;font-size:12px;margin-bottom:12px;">
        Topics: {escape(', '.join(topic_labels)) or '—'} &middot; Methods: {escape(', '.join(method_labels)) or '—'}
      </div>
      <div style="font-size:14px;line-height:1.6;color:#222;">{escape(brief)}</div>
    </div>
    """


def _render_email_html(subscriber: Subscriber, papers_with_briefs: list[tuple[dict, str]], taxonomies: dict) -> str:
    body = "".join(_render_paper_html(p, b, taxonomies) for p, b in papers_with_briefs)
    greeting = f"Hi {escape(subscriber.name)}," if subscriber.name else "Hi,"
    unsubscribe_mailto = "mailto:fqqqywzwan@gmail.com?subject=unsubscribe-journal-watch"
    return f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#222;">
  <h2 style="margin-top:0;">Journal Watch — weekly digest</h2>
  <p>{greeting}</p>
  <p>Here are {len(papers_with_briefs)} new paper{'s' if len(papers_with_briefs) != 1 else ''} matching your filter:</p>
  {body}
  <p style="font-size:11px;color:#888;margin-top:32px;">
    Filter: topics={escape(', '.join(subscriber.topics) or 'any')}, methods={escape(', '.join(subscriber.methods) or 'any')}, min relevance {subscriber.min_relevance}.<br>
    To unsubscribe, <a href="{unsubscribe_mailto}">click here</a> (sends an email to the list maintainer).
  </p>
</body></html>"""


def _send_email(to_email: str, subject: str, html_body: str):
    sender = os.environ["GMAIL_SENDER_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["From"] = f"Journal Watch <{sender}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content("Your email client does not support HTML. Please view in a modern client.")
    msg.add_alternative(html_body, subtype="html")
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
        server.login(sender, password)
        server.send_message(msg)


def run():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    if not os.environ.get("GMAIL_APP_PASSWORD"):
        raise SystemExit("GMAIL_APP_PASSWORD not set")
    if not os.environ.get("GMAIL_SENDER_ADDRESS"):
        raise SystemExit("GMAIL_SENDER_ADDRESS not set")

    taxonomies = _load_taxonomies()
    subscribers = fetch_subscribers(taxonomies)
    if not subscribers:
        print("No subscribers — nothing to send.")
        return

    db.init()
    with db.conn() as c:
        candidates = _candidate_papers(c, LOOKBACK_DAYS)

    if not candidates:
        print("No candidate papers in lookback window.")
        return

    print(f"{len(subscribers)} subscribers, {len(candidates)} candidate papers")
    client = Anthropic(api_key=api_key)
    brief_cache: dict[str, str] = {}

    for sub in subscribers:
        with db.conn() as c:
            matched = []
            for p in candidates:
                if not sub.matches(p["topics"], p["methods"], p["relevance"]):
                    continue
                if _already_sent(c, p["doi"], sub.email):
                    continue
                matched.append(p)
                if len(matched) >= MAX_PAPERS_PER_DIGEST:
                    break

        if not matched:
            print(f"  [{sub.email}] no matches")
            continue

        papers_with_briefs = []
        for p in matched:
            if p["doi"] not in brief_cache:
                brief_cache[p["doi"]] = _generate_brief(client, p)
            papers_with_briefs.append((p, brief_cache[p["doi"]]))

        html = _render_email_html(sub, papers_with_briefs, taxonomies)
        subject = f"Journal Watch — {len(matched)} new paper{'s' if len(matched) != 1 else ''}"
        _send_email(sub.email, subject, html)
        sub_hash = _email_hash(sub.email)
        with db.conn() as c:
            for p in matched:
                c.execute(
                    "INSERT OR IGNORE INTO digest_log (doi, subscriber_hash) VALUES (?, ?)",
                    (p["doi"], sub_hash),
                )
        print(f"  [{sub.email}] sent {len(matched)} papers")


if __name__ == "__main__":
    run()
