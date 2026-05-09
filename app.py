"""Streamlit browse UI for Journal Watch.

Run locally: streamlit run app.py
"""
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import yaml

from auth import require_password

DB_PATH = Path(__file__).parent / "data" / "papers.db"
TAX_PATH = Path(__file__).parent / "data" / "taxonomies.yaml"
JOURNALS_PATH = Path(__file__).parent / "data" / "journals.yaml"

st.set_page_config(page_title="Journal Watch", page_icon="📚", layout="wide")
require_password()


@st.cache_data(ttl=300)
def load_taxonomies():
    return yaml.safe_load(TAX_PATH.read_text())


@st.cache_data(ttl=300)
def load_journals():
    cfg = yaml.safe_load(JOURNALS_PATH.read_text())
    out = {}
    for journals in cfg.values():
        for j in journals:
            out[j["code"]] = j["name"]
    return out


@st.cache_data(ttl=60)
def load_papers():
    if not DB_PATH.exists():
        return []
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """SELECT p.doi, p.title, p.abstract, p.authors_json, p.journal_code, p.pub_date,
                  cls.topics_json, cls.methods_json, cls.relevance, cls.classified_at
           FROM papers p
           LEFT JOIN classifications cls ON cls.doi = p.doi
           ORDER BY p.pub_date DESC"""
    ).fetchall()
    c.close()
    papers = []
    for r in rows:
        papers.append({
            "doi": r["doi"],
            "title": r["title"],
            "abstract": r["abstract"] or "",
            "authors": json.loads(r["authors_json"] or "[]"),
            "journal_code": r["journal_code"],
            "pub_date": r["pub_date"],
            "topics": json.loads(r["topics_json"]) if r["topics_json"] else [],
            "methods": json.loads(r["methods_json"]) if r["methods_json"] else [],
            "relevance": r["relevance"] if r["relevance"] is not None else None,
            "classified": r["classified_at"] is not None,
        })
    return papers


def main():
    tax = load_taxonomies()
    journals = load_journals()
    papers = load_papers()

    st.title("📚 Journal Watch")
    st.caption(
        f"{len(papers):,} papers across {len(journals)} journals · "
        f"{sum(1 for p in papers if p['classified']):,} classified · "
        "Agri-Food Chain Management group, HU Berlin"
    )

    if not papers:
        st.warning("No papers in database yet. Run `python -m src.fetch` first.")
        return

    # ---------- Sidebar filters ----------
    st.sidebar.header("Filters")

    topic_codes = [t["code"] for t in tax["topics"]]
    topic_label = {t["code"]: t["label"] for t in tax["topics"]}
    selected_topics = st.sidebar.multiselect(
        "Topics",
        options=topic_codes,
        format_func=lambda c: topic_label[c],
        help="Match papers tagged with ANY selected topic. Leave empty for all.",
    )

    method_codes = [m["code"] for m in tax["methods"]]
    method_label = {m["code"]: m["label"] for m in tax["methods"]}
    selected_methods = st.sidebar.multiselect(
        "Methods",
        options=method_codes,
        format_func=lambda c: method_label[c],
        help="Match papers tagged with ANY selected method. Leave empty for all.",
    )

    min_relevance = st.sidebar.slider("Minimum relevance", 0, 10, 5)

    journal_filter = st.sidebar.multiselect(
        "Journals",
        options=sorted(journals.keys()),
        format_func=lambda c: f"{c} — {journals[c]}",
    )

    today = date.today()
    date_from = st.sidebar.date_input(
        "Published after",
        value=today - timedelta(days=180),
        min_value=date(2000, 1, 1),
        max_value=today,
    )

    show_unclassified = st.sidebar.checkbox(
        "Include unclassified papers", value=False,
        help="Show papers that haven't been classified yet (will appear without tags)."
    )

    keyword = st.sidebar.text_input(
        "Keyword (title or abstract)",
        placeholder="e.g., Kenya, conjoint, organic",
        help="Case-insensitive substring match. Combines with the other filters (AND).",
    ).strip().lower()

    # ---------- Apply filters ----------
    def matches(p):
        if not show_unclassified and not p["classified"]:
            return False
        if p["classified"]:
            if (p["relevance"] or 0) < min_relevance:
                return False
            if selected_topics and not (set(selected_topics) & set(p["topics"])):
                return False
            if selected_methods and not (set(selected_methods) & set(p["methods"])):
                return False
        if journal_filter and p["journal_code"] not in journal_filter:
            return False
        if p["pub_date"] < date_from.isoformat():
            return False
        if keyword and keyword not in p["title"].lower() and keyword not in p["abstract"].lower():
            return False
        return True

    filtered = [p for p in papers if matches(p)]

    # ---------- Top bar ----------
    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        sort_by = st.selectbox(
            "Sort by",
            ["Relevance (desc)", "Date (newest)", "Date (oldest)", "Journal"],
            label_visibility="collapsed",
        )
    with cols[1]:
        st.metric("Matching", f"{len(filtered):,}")
    with cols[2]:
        if filtered:
            avg_rel = sum((p["relevance"] or 0) for p in filtered if p["classified"])
            cls_count = sum(1 for p in filtered if p["classified"])
            st.metric("Avg relevance", f"{avg_rel/cls_count:.1f}" if cls_count else "—")
    with cols[3]:
        st.download_button(
            "Download CSV",
            data=_to_csv(filtered, topic_label, method_label),
            file_name="journal-watch.csv",
            mime="text/csv",
            disabled=not filtered,
        )

    if sort_by == "Relevance (desc)":
        filtered.sort(key=lambda p: p["pub_date"], reverse=True)
        filtered.sort(key=lambda p: -(p["relevance"] or -1))
    elif sort_by == "Date (newest)":
        filtered.sort(key=lambda p: p["pub_date"], reverse=True)
    elif sort_by == "Date (oldest)":
        filtered.sort(key=lambda p: p["pub_date"])
    elif sort_by == "Journal":
        filtered.sort(key=lambda p: (p["journal_code"], p["pub_date"]), reverse=True)

    if not filtered:
        st.info("No papers match the current filter.")
        return

    # ---------- Paper list ----------
    page_size = 25
    page = st.number_input("Page", min_value=1, max_value=max(1, (len(filtered) - 1) // page_size + 1), value=1)
    start = (page - 1) * page_size
    for p in filtered[start:start + page_size]:
        _render_paper(p, journals, topic_label, method_label)


def _to_csv(papers, topic_label, method_label):
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["pub_date", "journal", "title", "authors", "topics", "methods", "relevance", "doi"])
    for p in papers:
        w.writerow([
            p["pub_date"],
            p["journal_code"],
            p["title"],
            "; ".join(p["authors"]),
            "; ".join(topic_label.get(t, t) for t in p["topics"]),
            "; ".join(method_label.get(m, m) for m in p["methods"]),
            p["relevance"] if p["relevance"] is not None else "",
            f"https://doi.org/{p['doi']}",
        ])
    return buf.getvalue()


def _render_paper(p, journals, topic_label, method_label):
    journal_name = journals.get(p["journal_code"], p["journal_code"])
    authors = ", ".join(p["authors"][:5])
    if len(p["authors"]) > 5:
        authors += " et al."

    rel_badge = ""
    if p["classified"] and p["relevance"] is not None:
        color = "#1a8c4a" if p["relevance"] >= 7 else ("#d4790a" if p["relevance"] >= 4 else "#888")
        rel_badge = f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">rel {p["relevance"]}/10</span>'

    with st.container():
        st.markdown(
            f'### [{p["title"]}](https://doi.org/{p["doi"]}) {rel_badge}',
            unsafe_allow_html=True,
        )
        st.caption(f"{authors} · *{journal_name}* ({p['journal_code']}) · {p['pub_date']}")

        if p["classified"]:
            tags = []
            tags += [f'<span style="background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px;">{topic_label.get(t, t)}</span>' for t in p["topics"]]
            tags += [f'<span style="background:#f3e5f5;color:#6a1b9a;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px;">{method_label.get(m, m)}</span>' for m in p["methods"]]
            if tags:
                st.markdown("".join(tags), unsafe_allow_html=True)
        else:
            st.caption("_unclassified_")

        if p["abstract"]:
            with st.expander("Abstract"):
                st.write(p["abstract"])
        st.divider()


if __name__ == "__main__":
    main()
