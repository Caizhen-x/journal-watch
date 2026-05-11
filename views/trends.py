"""Trends page — topic/method evolution over time."""
import json
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import yaml

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "papers.db"
TAX_PATH = REPO_ROOT / "data" / "taxonomies.yaml"
JOURNALS_PATH = REPO_ROOT / "data" / "journals.yaml"


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


@st.cache_data(ttl=120)
def load_classified_papers() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """SELECT p.doi, p.journal_code, p.pub_date,
                  cls.topics_json, cls.methods_json, cls.relevance
           FROM papers p
           JOIN classifications cls ON cls.doi = p.doi"""
    ).fetchall()
    c.close()
    records = []
    for r in rows:
        year = r["pub_date"][:4]
        for t in json.loads(r["topics_json"]):
            records.append({"doi": r["doi"], "journal": r["journal_code"], "year": int(year), "kind": "topic", "tag": t, "relevance": r["relevance"]})
        for m in json.loads(r["methods_json"]):
            records.append({"doi": r["doi"], "journal": r["journal_code"], "year": int(year), "kind": "method", "tag": m, "relevance": r["relevance"]})
    return pd.DataFrame(records)


@st.cache_data(ttl=120)
def load_paper_summaries() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """SELECT p.doi, p.title, p.authors_json, p.journal_code, p.pub_date,
                  cls.relevance, cls.topics_json
           FROM papers p
           JOIN classifications cls ON cls.doi = p.doi"""
    ).fetchall()
    c.close()
    return pd.DataFrame([{
        "doi": r["doi"], "title": r["title"],
        "authors": ", ".join((json.loads(r["authors_json"] or "[]"))[:3]),
        "journal": r["journal_code"], "pub_date": r["pub_date"],
        "year": int(r["pub_date"][:4]), "relevance": r["relevance"],
        "topics": json.loads(r["topics_json"]),
    } for r in rows])


tax = load_taxonomies()
journals = load_journals()
df = load_classified_papers()
summaries = load_paper_summaries()

st.title("📊 Trends — Ag/Env Econ Literature")

if df.empty:
    st.warning("No classified papers yet. Run the classifier first (`python -m src.classify`).")
    st.stop()

topic_label = {t["code"]: t["label"] for t in tax["topics"]}
method_label = {m["code"]: m["label"] for m in tax["methods"]}

years_avail = sorted(df["year"].unique())
yr_min, yr_max = int(min(years_avail)), int(max(years_avail))
if yr_min == yr_max:
    st.info(f"Only {yr_min} data so far. Trend lines need at least 2 years; backfill to see trends.")
    yr_range = (yr_min, yr_max)
else:
    yr_range = st.slider("Year range", min_value=yr_min, max_value=yr_max, value=(max(yr_min, yr_max - 9), yr_max))

df = df[(df["year"] >= yr_range[0]) & (df["year"] <= yr_range[1])]
summaries = summaries[(summaries["year"] >= yr_range[0]) & (summaries["year"] <= yr_range[1])]

cols = st.columns(4)
cols[0].metric("Papers classified", f"{summaries['doi'].nunique():,}")
cols[1].metric("Year range", f"{yr_range[0]}–{yr_range[1]}")
cols[2].metric("Avg relevance", f"{summaries['relevance'].mean():.1f}")
cols[3].metric("Journals active", f"{df['journal'].nunique()}")

tab_topic, tab_method, tab_heatmap, tab_top, tab_journal = st.tabs(
    ["Topics over time", "Methods over time", "Journal × topic", "Top by year", "Per-journal volume"]
)

with tab_topic:
    st.caption("Number of papers tagged with each topic, by year. A paper can carry multiple topics.")
    topic_df = df[df["kind"] == "topic"].copy()
    topic_df["topic_label"] = topic_df["tag"].map(topic_label).fillna(topic_df["tag"])
    all_topics = sorted(topic_df["topic_label"].unique())
    selected = st.multiselect("Topics to show (default: all)", all_topics, default=all_topics, key="trend_topics")
    plot = topic_df[topic_df["topic_label"].isin(selected)]
    agg = plot.groupby(["year", "topic_label"])["doi"].nunique().reset_index(name="papers")
    chart_kind = st.radio("Chart type", ["Stacked area", "Lines", "Normalized share"], horizontal=True, key="trend_kind_topic")
    if chart_kind == "Stacked area":
        chart = alt.Chart(agg).mark_area().encode(x=alt.X("year:O", title="Year"), y=alt.Y("papers:Q", title="Papers"), color=alt.Color("topic_label:N", title="Topic"), tooltip=["year", "topic_label", "papers"])
    elif chart_kind == "Lines":
        chart = alt.Chart(agg).mark_line(point=True).encode(x=alt.X("year:O", title="Year"), y=alt.Y("papers:Q", title="Papers"), color=alt.Color("topic_label:N", title="Topic"), tooltip=["year", "topic_label", "papers"])
    else:
        chart = alt.Chart(agg).mark_area().encode(x=alt.X("year:O", title="Year"), y=alt.Y("papers:Q", title="Share of tagged papers", stack="normalize"), color=alt.Color("topic_label:N", title="Topic"), tooltip=["year", "topic_label", "papers"])
    st.altair_chart(chart.properties(height=420), use_container_width=True)

with tab_method:
    st.caption("Method adoption — useful to track e.g. DiD vs IV vs structural over time.")
    method_df = df[df["kind"] == "method"].copy()
    method_df["method_label"] = method_df["tag"].map(method_label).fillna(method_df["tag"])
    method_counts = method_df["method_label"].value_counts()
    default_methods = method_counts.head(8).index.tolist()
    selected_m = st.multiselect("Methods to show", sorted(method_df["method_label"].unique()), default=default_methods, key="trend_methods")
    plot_m = method_df[method_df["method_label"].isin(selected_m)]
    agg_m = plot_m.groupby(["year", "method_label"])["doi"].nunique().reset_index(name="papers")
    chart_m = alt.Chart(agg_m).mark_line(point=True).encode(x=alt.X("year:O", title="Year"), y=alt.Y("papers:Q", title="Papers using method"), color=alt.Color("method_label:N", title="Method"), tooltip=["year", "method_label", "papers"]).properties(height=420)
    st.altair_chart(chart_m, use_container_width=True)

with tab_heatmap:
    st.caption("Which journals publish what. Counts of unique papers tagged with each topic per journal in the selected years.")
    topic_df = df[df["kind"] == "topic"].copy()
    topic_df["topic_label"] = topic_df["tag"].map(topic_label)
    heat = topic_df.groupby(["journal", "topic_label"])["doi"].nunique().reset_index(name="papers")
    chart_h = alt.Chart(heat).mark_rect().encode(x=alt.X("topic_label:N", title="Topic", axis=alt.Axis(labelAngle=-40)), y=alt.Y("journal:N", title="Journal"), color=alt.Color("papers:Q", title="Papers", scale=alt.Scale(scheme="blues")), tooltip=["journal", "topic_label", "papers"]).properties(height=520)
    st.altair_chart(chart_h, use_container_width=True)

with tab_top:
    st.caption(f"Highest-relevance paper of each year in {yr_range[0]}–{yr_range[1]}.")
    if summaries.empty:
        st.info("No data in window.")
    else:
        top_by_year = summaries.sort_values(["year", "relevance"], ascending=[True, False]).groupby("year").head(3)
        for year, group in top_by_year.groupby("year", sort=False):
            st.markdown(f"### {year}")
            for _, r in group.iterrows():
                st.markdown(f"- **rel {r['relevance']}/10** · [{r['title']}](https://doi.org/{r['doi']}) — *{r['journal']}*, {r['pub_date']} — {r['authors']}")

with tab_journal:
    st.caption("Classified paper volume per journal per year. Useful to spot coverage gaps.")
    vol = summaries.groupby(["year", "journal"])["doi"].nunique().reset_index(name="papers")
    chart_v = alt.Chart(vol).mark_bar().encode(x=alt.X("year:O"), y=alt.Y("papers:Q", title="Papers"), color=alt.Color("journal:N", title="Journal"), tooltip=["journal", "year", "papers"]).properties(height=420)
    st.altair_chart(chart_v, use_container_width=True)
