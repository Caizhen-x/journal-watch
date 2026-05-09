# Journal Watch

Automated journal watch for the **Agri-Food Chain Management** group at Humboldt-Universität zu Berlin.

Polls top journals daily, classifies new papers by **topic × method** using an LLM, and emails a weekly digest of matching papers to subscribed group members.

## How it works

```
[GitHub Actions, daily]
    ↓
Fetch new papers from Crossref / OpenAlex / Semantic Scholar (by ISSN)
    ↓
LLM classifier tags each paper with topics[] + methods[] + relevance score
    ↓
SQLite (committed back to repo for state persistence)
    ↓
[GitHub Actions, weekly]
    ↓
For each subscriber's saved filter → render briefs → send via Gmail
```

## Repo layout

```
journal-watch/
├── data/
│   ├── journals.yaml      # journal registry with ISSNs (edit to add/remove journals)
│   ├── taxonomies.yaml    # topic + method taxonomies (edit to refine classification)
│   └── papers.db          # SQLite, populated by Phase 2 fetcher
├── src/                   # Phase 2: fetcher, classifier, digest builder
└── .github/workflows/     # Phase 3: cron schedules
```

## Status

- [x] Phase 1: foundation — journal list + taxonomies
- [x] Phase 2: fetcher (OpenAlex) + classifier (Claude Haiku)
- [x] Phase 3: weekly email digest + Google Form subscriber registry
- [x] Phase 4: 12-month backfill + Streamlit browse UI

## Setup

See **[SETUP.md](SETUP.md)** for the one-time configuration (API keys, Gmail App Password, Google Form).

## Browse UI

Local Streamlit app for the topic × method filter view:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. Filters: topics (multi-select), methods (multi-select), minimum relevance, journal subset, date range. Sortable, with CSV export.

## Scope

Initial coverage is the 20 journals in `data/journals.yaml` (Agricultural Economics + Environmental & Resource Economics). Other domains from the parent project will be added after Phase 3 ships.
